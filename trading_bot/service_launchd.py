"""Pure plist rendering, explicit GUI lifecycle and durable pre-worker admission."""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess

from .service_config import ServiceSettings, protected_file, load_service_settings
from .service_leader import ServiceLeader, ServiceRestartDenied
from .service_models import OwnerLoginEvidence, ServiceContract, InstallationScope, Identity
from .web_config import checked_path, overlaps

SERVICE_LABEL='com.stock-trading-bot.service'
ALERT_LABEL='com.stock-trading-bot.alerts'
LABELS=(SERVICE_LABEL,ALERT_LABEL)


def _clock(): return datetime.now(timezone.utc)


def render_launchagents(settings,*,config_path,working_directory=None):
    """Read/configuration only; no files created and no OS process invoked."""
    if type(settings) is not ServiceSettings: raise TypeError('registered service settings required')
    config=protected_file(config_path)
    if load_service_settings(config)!=settings: raise ValueError('fixed protected registration required')
    work=checked_path(working_directory or Path(__file__).absolute().parents[1])
    if not work.is_dir() or work.stat().st_uid!=os.getuid() or work.stat().st_mode & 0o022:
        raise ValueError('owner controlled absolute working directory required')
    settings.validate_topology()
    interpreter=checked_path(settings.interpreter_path)
    logs=checked_path(settings.service_db_path).parent.parent/'logs'
    if any(overlaps(logs,checked_path(p).parent) for p in (*settings.trading_journal_paths,
            settings.control_db_path,config_path)): raise ValueError('separate protected log root required')
    result={}
    for label,module,extra in ((SERVICE_LABEL,'trading_bot.service_cli', ['--config',str(config),'launch']),
            (ALERT_LABEL,'trading_bot.alert_cli',['--config',str(checked_path(settings.observer_config_path)),
                '--expectation-service-config',str(config),'watch'])):
        document={'Label':label,'ProgramArguments':[str(interpreter),'-m',module,*extra],
            'WorkingDirectory':str(work),'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},
            'ThrottleInterval':10,'ExitTimeOut':30,
            'StandardOutPath':str(logs/f'{label}.stdout.log'),'StandardErrorPath':str(logs/f'{label}.stderr.log')}
        result[label]=plistlib.dumps(document,fmt=plistlib.FMT_XML,sort_keys=True)
    return result


def _call(runner,args,timeout=1):
    result=runner(['/bin/launchctl',*args],capture_output=True,text=True,timeout=timeout,check=False)
    if len(result.stdout.encode())>65536 or len(result.stderr.encode())>65536:
        raise ValueError('bounded launchctl output required')
    return result


def gui_login_probe(service_config,*,clock=_clock,runner=subprocess.run):
    """Construct only; an explicitly started installed observer performs print."""
    from .service_schedule import OwnerLoginProbe
    config=protected_file(service_config); uid=os.getuid(); domain=f'gui/{uid}'
    observation_started=None
    def probe_clock():
        nonlocal observation_started
        observation_started=clock()
        return observation_started
    def observe():
        protected_file(config)
        # OwnerLoginProbe validates against the bounded observation's start time.
        now=observation_started; result=_call(runner,['print',domain])
        text=result.stdout
        owners={int(x) for x in re.findall(r'\b(?:uid|user)\s*=\s*(\d+)\s*(?:;|\n)',text)}
        sessions=set(re.findall(r'\b(?:session(?: id)?|asid)\s*=\s*(\d+)\s*(?:;|\n)',text))
        if (result.returncode!=0 or not text.lstrip().startswith(domain+' = {')
                or not re.search(r'\btype\s*=\s*Login\s*(?:;|\n)',text)
                or owners!={uid} or len(sessions)!=1):
            raise ValueError('GUI owner session registration unknown')
        session=sessions.pop()
        return OwnerLoginEvidence(owner_uid=uid,gui_session_id=f'gui:{uid}:{session}',
            source_id=f'launchctl-gui-{uid}',observed_at=now,effective_at=now,state='CONFIRMED')
    return OwnerLoginProbe(observe,clock=probe_clock,owner_uid=uid)


def _registered(runner,domain,label,path):
    result=_call(runner,['print',f'{domain}/{label}'])
    if result.returncode==113: return False
    if result.returncode!=0: raise ValueError('registration inspection unavailable')
    paths=re.findall(r'^\s*path\s*=\s*(.*?)\s*$',result.stdout,re.MULTILINE)
    if paths!=[str(path)]: raise ValueError('unrelated launch label collision')
    return True


def lifecycle_command(settings,*,config_path,command,agents_dir=None,runner=subprocess.run):
    if command not in ('render','install','start','stop','remove'): raise ValueError('explicit lifecycle action required')
    rendered=render_launchagents(settings,config_path=config_path)
    if command=='render':
        return {label:payload.decode('utf-8') for label,payload in rendered.items()}
    directory=checked_path(agents_dir or Path.home()/'Library'/'LaunchAgents')
    from .service_store import private_directory
    if directory.exists() and (not directory.is_dir() or directory.stat().st_uid!=os.getuid()
            or directory.stat().st_mode & 0o022): raise ValueError('owner GUI LaunchAgents directory required')
    domain=f'gui/{os.getuid()}'
    if gui_login_probe(config_path,runner=runner).observe_owner_gui().state!='CONFIRMED':
        raise ValueError('owner GUI registration unknown')
    paths={label:directory/f'{label}.plist' for label in LABELS}
    # Inspect both collisions before any mutation, including the independent observer.
    installed={}
    for label,path in paths.items():
        if path.exists():
            if protected_file(path).read_bytes()!=rendered[label]: raise ValueError('unrelated plist collision')
        elif command!='install': raise ValueError('owned installed plist required')
        installed[label]=_registered(runner,domain,label,path)
    if command=='install':
        private_directory(directory)
        for label,path in paths.items():
            if not path.exists():
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'wb') as file:
                    file.write(rendered[label]);file.flush();os.fsync(file.fileno())
        logs=checked_path(settings.service_db_path).parent.parent/'logs';private_directory(logs)
        for label in LABELS:
            for suffix in ('stdout','stderr'):
                logfile=logs/f'{label}.{suffix}.log'
                if logfile.exists(): protected_file(logfile)
                else:
                    fd=os.open(logfile,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
        # Observer is registered first, with its own supervision/budget.
        for label in (ALERT_LABEL,SERVICE_LABEL):
            if not installed[label] and _call(runner,['bootstrap',domain,str(paths[label])],timeout=5).returncode!=0:
                raise ValueError('GUI bootstrap failed')
    elif command=='start':
        for label in (ALERT_LABEL,SERVICE_LABEL):
            if not installed[label]:
                if _call(runner,['bootstrap',domain,str(paths[label])],timeout=5).returncode!=0:
                    raise ValueError('GUI bootstrap failed')
            if _call(runner,['kickstart',f'{domain}/{label}'],timeout=5).returncode!=0:
                raise ValueError('GUI start failed')
    else:
        # Stopping the trading service keeps the observer available. Removal stops both.
        selected=LABELS if command=='remove' else (SERVICE_LABEL,)
        for label in selected:
            if installed[label] and _call(runner,['bootout',f'{domain}/{label}'],timeout=30).returncode!=0:
                raise ValueError('GUI stop failed')
        if command=='remove':
            for label,path in paths.items():
                if protected_file(path).read_bytes()!=rendered[label]: raise ValueError('plist changed during removal')
                path.unlink()
    return {'action':command,'domain':domain,'evidence':'retained','labels':list(LABELS)}


def _consume_attention_request(settings,journal,runtime_factory,*,clock):
    """Explicit reset is validated by service ownership and fresh concrete recovery."""
    from pydantic import AwareDatetime,Field
    from .service_cli import attention_request_path,attention_history_path,owner_actor,private_write
    from .service_activation import _protected_json
    from .service_store import protected_descriptor,private_directory
    from .service_runtime import ServiceRuntime
    from .submission_authority import OwnedActivationCheck
    from .web_store import timestamp
    request_path=attention_request_path(settings)
    if not request_path.exists(): return False
    class ResetRequest(ServiceContract):
        schema_version:int=Field(ge=1,le=1,strict=True)
        action:str=Field(pattern='^RESET_ATTENTION$')
        request_id:Identity
        actor:Identity
        requested_at:AwareDatetime
        expected_revision:int=Field(ge=0,strict=True)
        scope:InstallationScope
    request=ResetRequest.model_validate(_protected_json(request_path,65536))
    if (request.actor!=owner_actor() or request.scope.registered_scopes!=InstallationScope(
            registered_scopes=settings.registered_scopes).registered_scopes or request.requested_at>clock()):
        raise ValueError('registered explicit reset actor/scope/time required')
    with journal.connection() as conn:
        attention=conn.execute('SELECT * FROM service_attention_events ORDER BY event_id DESC LIMIT 1').fetchone()
        last=conn.execute('SELECT MAX(admitted_at) FROM service_restart_attempts').fetchone()[0]
        if (attention is None or attention['state']!='MANUAL_ATTENTION'
                or timestamp(clock())-max(attention['observed_at'],last or attention['observed_at'])<600): return False
        if timestamp(request.requested_at)<attention['observed_at']: raise ValueError('reset predates attention episode')
    # Keep the same OS leader flock throughout reset recovery; no live service overlap.
    lock=checked_path(settings.lock_dir)/'service-leader.lock';private_directory(lock.parent)
    fd=protected_descriptor(lock,create=True);runtime=None
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        runtime=runtime_factory(settings)
        if (type(runtime) is not ServiceRuntime or type(runtime.activation_check) is not OwnedActivationCheck
                or runtime.settings!=settings): raise ValueError('concrete owned reset runtime required')
        verdict=runtime.activation_check()
        if not verdict.allowed or verdict.authority!='OWNED_KIS_OBSERVED': return False
        # No trading operation is passed; fresh recovery/reconciliation must fully release.
        runtime.work.run(lambda lease,current,budget:current)
        from .control_store import ControlStore
        controls=ControlStore(settings,clock=clock)
        with controls.admission_lock():
            if controls.reader().effective_state().acceptance_revision!=request.expected_revision: return False
            verdict=runtime.activation_check()
            if not verdict.allowed or verdict.authority!='OWNED_KIS_OBSERVED': return False
            history=attention_history_path(settings,request.request_id)
            private_write(history,request.model_dump(mode='json'))
            if ResetRequest.model_validate(_protected_json(request_path,65536))!=request: raise ValueError('reset request changed')
            if not journal.request_attention_reset(safety_validated=True,recovery_validated=True,observed_at=clock()): return False
            request_path.unlink()
        return True
    finally:
        if runtime is not None and hasattr(runtime,'close_resources'): runtime.close_resources()
        os.close(fd)


def launch_worker(settings,*,runtime_factory=None,clock=_clock,offline_authority=None):
    """Leadership/restart admission commit precedes credential or worker construction."""
    from .service_store import ServiceJournal
    from .service_activation import OfflineActivationAuthority
    if offline_authority is not None:
        if type(offline_authority) is not OfflineActivationAuthority: raise ValueError('temporary fixture authority required')
        offline_authority.assert_settings(settings)
    if (not settings.service_enabled or settings.mode=='DISABLED') and offline_authority is None: return 'DISABLED'
    if settings.mode!='KIS_MOCK' and offline_authority is None: raise ValueError('explicit mock service required')
    if runtime_factory is None:
        from .service_cli import build_production_runtime
        runtime_factory=build_production_runtime
    journal=ServiceJournal(settings,clock=clock)
    if offline_authority is None:
        try:
            _consume_attention_request(settings,journal,runtime_factory,clock=clock)
        except (Exception,):
            # A failed/malformed explicit reset cannot create an unbudgeted launch loop.
            from .web_store import timestamp
            with journal.connection() as conn:
                conn.execute('INSERT INTO service_attention_events(state,reason_code,observed_at) '
                    'VALUES(?,?,?)',('MANUAL_ATTENTION','RESET_VALIDATION_FAILED',timestamp(clock())))
            return 'MANUAL_ATTENTION'
    leader=ServiceLeader(settings,journal=journal)
    try: leader.acquire()
    except ServiceRestartDenied: return 'MANUAL_ATTENTION'
    runtime=None
    try:
        runtime=runtime_factory(settings)
        from .service_runtime import ServiceRuntime
        if type(runtime) is not ServiceRuntime: raise ValueError('concrete installed service runtime required')
        runtime.bind_admitted_leader(leader)
        runtime.run()
        leader.close(clean_stop=True)
        return 'STOPPED'
    except BaseException:
        # Constructor/startup crashes count and remain unexpected for the next admission.
        leader.close(clean_stop=False)
        raise
    finally:
        if runtime is not None and hasattr(runtime,'close_resources'): runtime.close_resources()

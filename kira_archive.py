"""Read-only access to preserved conversations and generated files from older Kira versions."""
import hashlib
import json
import os
from pathlib import Path
import stat
from kira_jobs import JobError, identifier

def conversation_read(root, conversation):
    identifier(conversation)
    parent = os.open(Path(root) / 'conversations', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:fd = os.open(conversation + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:os.close(parent)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 500000:raise JobError('invalid_archive','Choose a regular saved conversation under 500 KB.')
        body = stream.read(500001)
    try:
        value = json.loads(body)
        messages = value['messages']
        if value.get('schema_version') != 1 or value.get('conversation_id') != conversation or not isinstance(messages,list) or len(messages)>24:raise ValueError()
        if any(not isinstance(m,dict) or set(m)!={'role','text'} or m['role'] not in ('user','assistant') or not isinstance(m['text'],str) for m in messages):raise ValueError()
        if sum(len(m['text'].encode()) for m in messages)>400000:raise ValueError()
        return {'conversation_id':conversation,'messages':messages,
                'started_at':value.get('started_at'),'updated_at':value.get('updated_at')}
    except (ValueError, TypeError, KeyError, RecursionError):
        raise JobError('invalid_archive','This saved conversation is not a supported archive.') from None


def conversations(root):
    result=[]
    folder=Path(root)/'conversations'
    if not folder.is_dir() or folder.is_symlink():return result
    for path in folder.glob('*.json'):
        try:
            value=conversation_read(root,path.stem)
            result.append({k:v for k,v in value.items() if k!='messages'})
        except (OSError,ValueError):continue
    return sorted(result,key=lambda r:r.get('updated_at') or '',reverse=True)


def workspace_list(root):
    import uuid
    folder=workspace_path(root,str(uuid.UUID(int=0))).parent
    if not folder.is_dir() or folder.is_symlink() or folder.parent.is_symlink():return []
    result=[]
    for path in folder.iterdir():
        try:identifier(path.name)
        except JobError:continue
        if path.is_dir() and not path.is_symlink():result.append(path.name)
    return sorted(result)

def workspace_path(root,conversation):
    from kira_jobs import identifier
    identifier(conversation)
    root=Path(root).resolve()
    key=hashlib.sha256(str(root).encode()).hexdigest()[:16]
    return root.parent/'kira-agent-workspaces'/key/conversation

def artifacts(root,conversation):
    workspace=workspace_path(root,conversation)
    if not workspace.is_dir() or any(p.is_symlink() for p in (workspace,workspace.parent,workspace.parent.parent)):return []
    result=[];count=0
    for folder,dirs,files in os.walk(workspace,followlinks=False):
        count+=1
        if count>200:return result
        dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(folder)/d).is_symlink()][:50]
        for name in files:
            count+=1
            if count>200:return result
            path=Path(folder)/name
            try:
                info=path.lstat()
                if name.startswith('.') or not stat.S_ISREG(info.st_mode) or info.st_size>20_000_000:continue
                result.append({'path':str(path.relative_to(workspace)),'size':info.st_size})
            except OSError:continue
    return result

def read_artifact(root,conversation,name):
    if not isinstance(name,str) or len(name)>2000 or Path(name).is_absolute() or '..' in Path(name).parts:raise JobError('invalid_file','Choose a file in this conversation workspace.')
    workspace=workspace_path(root,conversation)
    # Walk open directories so concurrent symlink replacement cannot redirect a download.
    parent=Path(root).resolve().parent
    descriptor=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
    try:
        parts=(*workspace.relative_to(parent).parts,*Path(name).parts)
        for part in parts[:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            os.close(descriptor);descriptor=child
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=descriptor)
    except OSError:
        raise JobError('invalid_file','Choose a regular file in this conversation workspace.') from None
    finally:os.close(descriptor)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>20_000_000:raise JobError('invalid_file','Choose a regular file under 20 MB.')
        body=stream.read(20_000_001)
        if len(body)>20_000_000:raise JobError('invalid_file','Choose a regular file under 20 MB.')
        return body

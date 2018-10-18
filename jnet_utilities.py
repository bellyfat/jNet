from subprocess import PIPE, Popen
import re, platform, warnings, json
import datetime, contextlib, sqlite3
import typing, tigerSqlite
import multiprocessing
import time, os

def test_passcode(_code:str) -> bool:
    '''only supported on Darwin'''
    if platform.system() == 'Darwin':
        text = f'{_code}\n'
        p = Popen(['sudo', '-k', '-S', '-p', '', 'ls'], stdin=PIPE, stderr=PIPE, universal_newlines=True)
        _, b = p.communicate(text)
        return not bool(re.findall('^Sorry, try again', b))
    warnings.warn('System not detected. Cannot check passcode')


def is_configured() -> bool:
    with open('browser_settings/__browser_settings__.json') as f:
        return json.load(f)["configured"]

def setup_browser(passcode:str, _data:dict) -> None:
    with open('browser_settings/__browser_settings__.json', 'w') as f:
        d = datetime.datetime.now()
        json.dump({'configured':True, 'user_info':{'root_password':passcode, 'configured_on':[getattr(d, i) for i in ['year', 'month', 'day', 'hour', 'minute', 'second']], **_data}}, f)


def get_root_passcode() -> str:
    with open('browser_settings/__browser_settings__.json') as f:
        _d = json.load(f)
        if _d['configured']:
            return _d['user_info']['root_password']



def get_full_username() -> str:
    with open('browser_settings/__browser_settings__.json') as f:
        _d = json.load(f)
        if _d['configured']:
            return f"{_d['user_info']['firstname']} {_d['user_info']['lastname']}"


def mute(f):
    return lambda *args, **kwargs:None


@contextlib.contextmanager
def add_server_hosting(name:str, _url:str):
    conn = sqlite3.connect('browser_settings/server_hostings.db')
    _d = datetime.datetime.now()
    _timestamp = '-'.join(str(getattr(_d, i)) for i in ['month', 'day', 'year'])+' '+':'.join(str(getattr(_d, i)) for i in ['hour', 'minute', 'second'])
    conn.execute("INSERT INTO servers VALUES (?, ?, ?)", [name, _url, _timestamp])
    conn.commit()
    conn.close()
    yield _timestamp


def find_tab(tab_num:int) -> typing.NamedTuple:
    class TabRow(typing.NamedTuple):
        tabid:int
        siteip:str
        appname:str
        url:str
        path:str
        sessions:dict
        #num real, ip text, app text, url text, path text, session text
    tabs = [i for i in tigerSqlite.Sqlite('browser_settings/browser_tabs.db').get_num_ip_app_url_path_session('tabs') if i[0] == tab_num]
    if tabs:
        return TabRow(*tabs[0])

def server_loc(_server_name:str) -> str:
    return [i for i in sqlite3.connect('browser_settings/server_hostings.db').cursor().execute("SELECT * FROM servers") if i[0] == _server_name][0][1]

def get_session(_tab_num:int) -> dict:
    return [b for a, b in tigerSqlite.Sqlite('browser_settings/browser_tabs.db').get_num_session('tabs') if a == _tab_num][0]

def log_history(f:typing.Callable):
    def wrapper(site_obj, url, _tab, update=False):
        d = datetime.datetime.now()
        timestamp = '-'.join(str(getattr(d, i)) for i in ['month', 'day', 'year'])+' '+':'.join(str(getattr(d, i)) for i in ['hour', 'minute', 'second'])
        #app text, path text, ip text, server text, timestamp text
        conn = sqlite3.connect('browser_settings/browser_history.db')
        conn.execute("INSERT INTO history VALUES (?, ?, ?, ?, ?)", [url.app_name, url.path, site_obj.ip, url.server, timestamp])
        conn.commit()
        conn.close()
        return f(site_obj, url, _tab, update=update)
    return wrapper


class TimedOut(Exception):
    pass

def terminate_delay(_time):
    def _wrapper(_f:typing.Callable):
        def __test_run(_func:typing.Callable, _queue, args, kwargs):
            _r = _func(*args, **kwargs)
            _queue.put({'_r_result':_r})
        
        def _main_wrapper(*args, **kwargs):
            _respond = multiprocessing.Queue()
            p = multiprocessing.Process(target=__test_run, name="Attempt_connect", args=(_f, _respond, args, kwargs))
            p.start()
            time.sleep(_time)
            p.terminate()
            p.join()
            try:
                _r = _respond.get(False)
            except:
                raise TimedOut(f'"{_f.__name__}" timed out after {_time} second{"s" if _time != 1 else ""}')
            else:
                return _r['_r_result']
        return _main_wrapper
    return _wrapper


def create_app(_name:str) -> None:
    d = datetime.datetime.now()
    _ = os.system(f'mkdir apps/app_{_name}')
    _timestamp = '-'.join(str(getattr(d, i)) for i in ['month', 'day', 'year'])+' '+':'.join(str(getattr(d, i)) for i in ['hour', 'minute', 'second'])
    with open(f'apps/app_{_name}/app_config.json', 'w') as f:
        json.dump({'live':False, 'created_on':[getattr(d, i) for i in ['year', 'month', 'day', 'hour', 'minute', 'second']]}, f)
    
    _ = os.system(f'mkdir apps/app_{_name}/templates')
    with open(f'apps/app_{_name}/templates/home.html', 'w') as f:
        f.write(open('jnet_static_folder/jnet_app_template.html').read())
    
    with open(f'apps/app_{_name}/templates/home_style.css', 'w') as f:
        f.write(open('jnet_static_folder/jnet_app_template_style.css').read())

    with open(f'apps/app_{_name}/templates/home_js.js', 'w') as f:
        f.write(open('jnet_static_folder/jnet_app_template_js.js').read())
    
    with open(f'apps/app_{_name}/log.txt', 'w') as f:
        f.write(f'{_timestamp}: app "{_name}" created\n')
    
    with open(f'apps/app_{_name}/app_routes.py', 'w') as f:
        f.write(open('app_main_template.py').read().format(_name))

    for _file in ['telemonius', 'telemonius_routes', 'telemonius_wrappers', 'telemonius_errors']:
        with open(f'apps/app_{_name}/{_file}.py', 'w') as f:
            f.write(open(f'_{_file}.py').read())
    

    conn = sqlite3.connect(f'apps/app_{_name}/__views__.db')
    conn.execute("CREATE TABLE views (timestamp text, ip text, visitor text, path text, server text)")
    conn.commit()
    conn.close()


def log_view(_f:typing.Callable) -> typing.Callable:
    #timestamp text, ip text, visitor text, path text, server text
    def _wrapper(_payload:dict):
        d = datetime.datetime.now()
        _timestamp = '-'.join(str(getattr(d, i)) for i in ['month', 'day', 'year']) + ' '+':'.join(str(getattr(d, i)) for i in ['hour', 'minute', 'second'])
        conn = sqlite3.connect(f'app/app_{_payload["app"]}/__views__.db')
        conn.execute("INSERT INTO views VALUES (?, ?, ?, ?, ?)", [_timestamp, _payload['ip'], _payload['sender'], _payload['path'], _payload['server']])
        conn.commit()
        conn.close()
        return _f(_payload)
    return _wrapper
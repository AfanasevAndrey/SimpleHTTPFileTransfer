#!/usr/bin/python3
'''
Простой и легкий HTTP сервер для скачивания и загрузки файлов.
Запускается из директории, эта директория становится доступна при подключении к серверу.
Для запуска нужен Python2.6 и выше.
Дополнительных модулей не требуется.
Лог сервера пишется в эту же директорию, если не указано иного.
'''

import html
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
import io
import logging
import cgi
import os
import sys
import urllib
import datetime
import email.utils
import re
import argparse
from typing import Union

# Корневая директория сервера
root_dir = os.getcwd()
# Возможные уровни логирования
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR

#-----------------------------------------------------------------------------
# Класс HTTP-сервера
#-----------------------------------------------------------------------------
class Server(SimpleHTTPRequestHandler):
    '''
    Класс HTTP сервера, предназначенного для обмена файлами по протоколу HTTP.
    Обрабатывает GET и POST запросы клиента. Дает доступ к директории, на которой запущен,
    позволяет перемещаться по вложенным директориям, скачивать и загружать находящиеся там
    файлы
    '''
    #-----------------------------------------------------------------------------
    # Метод получения вышестоящей директории
    #-----------------------------------------------------------------------------
    def get_prev_dir(self, path : str) -> Union[str, None]:
        '''
        Метод возвращает дерикторию уровнем выше чем запрошенная, если таковая существует 
        (если запрашивается не корневая для сервера директория)
        
        Входные параметры:
        path - строка, содержащая путь к запрошенной директори;

        Возвращает строку, содержащую путь к дириктории выше запрошенной или None, если
        была запрошена корневая для сервера директория
        '''
        logging.debug(f"Trying get uper directory for {path}")
        if path != root_dir:
            return path.replace(path.split('/')[-1],'').replace(root_dir,'')
        logging.debug(f"{path} is the upest directory")
        return None
    
    #-----------------------------------------------------------------------------
    # Метод отправки файла клиенту
    #-----------------------------------------------------------------------------
    def send_file(self, path : str) -> Union[io.BytesIO, None]:
        '''
        Метод отправки запрашиваемого файла клиенту. Вычитывает данные файла и подготавливает их
        к отправки внутри HTTP пакета

        Входные параметры:
        path - строка, содержащая абсолютный путь к запрошенному файлу;

        Возвращает объект двоичного потока ввода/вывода, содержащий файл или None если нет прав для доступа к файлу
        '''
        logging.debug(f'Trying to read file data for send. File {path}')
        # Указываем ctype для безусловного скачивания файла (возможно это не совсем корректно)
        ctype = 'application/octet-stream'
        # Пробуем открыть файл на чтение байтовое. Если не можем - возвращаем 404
        try:
            f = open(path, 'rb')
        except OSError:
            logging.warning(f"No permission to read file {path}")
            self.send_error(HTTPStatus.NOT_FOUND, "No permission to get file")
            return None
        try:
            # Пробуем получить файловые атрибуты по дескриптору файла
            fs = os.fstat(f.fileno())
            # По возможности пробуем использовать кэш
            if ("If-Modified-Since" in self.headers
                    and "If-None-Match" not in self.headers):
                # compare If-Modified-Since and time of last file modification
                try:
                    ims = email.utils.parsedate_to_datetime(
                        self.headers["If-Modified-Since"])
                except (TypeError, IndexError, OverflowError, ValueError):
                    # ignore ill-formed values
                    pass
                else:
                    if ims.tzinfo is None:
                        # obsolete format with no timezone, cf.
                        # https://tools.ietf.org/html/rfc7231#section-7.1.1.1
                        ims = ims.replace(tzinfo=datetime.timezone.utc)
                    if ims.tzinfo is datetime.timezone.utc:
                        # compare to UTC datetime of last modification
                        last_modif = datetime.datetime.fromtimestamp(
                            fs.st_mtime, datetime.timezone.utc)
                        # remove microseconds, like in If-Modified-Since
                        last_modif = last_modif.replace(microsecond=0)

                        if last_modif <= ims:
                            self.send_response(HTTPStatus.NOT_MODIFIED)
                            self.end_headers()
                            f.close()
                            return None
            # Отправляем ответ 200(ок), заголовки и возвращаем байтовый поток файла
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(fs[6]))
            self.send_header("Last-Modified",
                self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f
        except:
            logging.error(f"Error in get atributes for file {path}")
            f.close()
            self.send_error(HTTPStatus.NOT_FOUND, "Error in get atributes for file")
            return None

    #-----------------------------------------------------------------------------
    # Формируем HTML страницу, содержащую наполнение запрашиваемой директории
    #-----------------------------------------------------------------------------
    def list_directory(self, path : str) -> Union[io.BytesIO, None]:
        """
        Helper to produce a directory listing (absent index.html).

        Return value is either a file object, or None (indicating an
        error).  In either case, the headers are sent, making the
        interface the same as for send_head().
        
        Метод формирует HTML страницу, содержащую список содержимого дериктории в виде ссылок

        Входные параметры:
        path - строка, содержащая абсолютный путь к запрошенной директории;

        Возвращает объект потока двоичного ввода/вывода в случае успеха или None в случае ошибки
        """
        logging.debug(f"Start forming HTML page with list of requsted directory content: {path}")
        # Проверяем права для доступа к директории. В случае неудачи - возвращаем ошибку
        try:
            list = os.listdir(path)
        except OSError:
            logging.warning(f"No permisson to directory {path}")
            self.send_error(
                HTTPStatus.NOT_FOUND,
                "No permission to list directory")
            return None
        # Получаем директорию уровня выше чтобы сформировать ссылку на нее
        prev_dir = self.get_prev_dir(path)
        # Сортируем содержимое директории
        list.sort(key=lambda a: a.lower())
        # В этом списке хранится сформированная HTML страница
        r = []
        # Переводим URL адрес запрошенной директории в строку (убираем escape последовательности)
        try:
            displaypath = urllib.parse.unquote(self.path,
                                               errors='surrogatepass')
        except UnicodeDecodeError:
            displaypath = urllib.parse.unquote(path)
        # Экранируем путь директории для передачи внутри HTML страницы    
        displaypath = html.escape(displaypath, quote=False)
        # Получаем кодировку, используемую в системе, нужно для указания в HTML странице
        enc = sys.getfilesystemencoding()
        # Формируем непосредственно страницу
        title = f'Directory listing for {displaypath}'
        r.append('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" '
                 '"http://www.w3.org/TR/html4/strict.dtd">')
        r.append('<html>\n<head>')
        r.append('<meta http-equiv="Content-Type" '
                 f'content="text/html; charset={enc}">')
        r.append(f'<title>{title}</title>\n</head>')
        r.append(f'<body>\n<h1>{title}</h1>')
        r.append('<hr>\n<ul>')
        r.append('<form enctype="multipart/form-data" method="post">')
        r.append('<p><input type="file" name="datafile" multiple>')
        r.append('<input type="submit" value="Отправить"></p>')
        r.append('</form> ')
        # Если есть путь к директории выше, то преобразуем его в ссылку и добавляем в страницу
        if prev_dir:
            r.append('<li><a href="%s">%s</a></li>'
            % (urllib.parse.quote(prev_dir,
                                    errors='surrogatepass'),
                html.escape('..', quote=False)))
        # Преобразуем все содержимое директории в ссылки и добавляем к странице    
        for name in list:
            fullname = os.path.join(path, name)
            displayname = linkname = name
            # Append / for directories or @ for symbolic links
            if os.path.isdir(fullname):
                displayname = name + "/"
                linkname = name + "/"
            if os.path.islink(fullname):
                displayname = name + "@"
                # Note: a link to a directory displays with @ and links with /
            r.append('<li><a href="%s">%s</a></li>'
                    % (urllib.parse.quote(linkname,
                                          errors='surrogatepass'),
                       html.escape(displayname, quote=False)))
            
        r.append('</ul>\n<hr>\n</body>\n</html>\n')
        # Кодируем страницу кодировкой ОС, так как двоичный поток ввода/вывода требует на вход
        # двоичную строку
        encoded = '\n'.join(r).encode(enc, 'surrogateescape')
        # Открываем поток, отправляем ответ, заголовки и возвращаем поток
        f = io.BytesIO()
        f.write(encoded)
        f.seek(0)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-type", "text/html; charset=%s" % enc)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        return f
    
    #-----------------------------------------------------------------------------
    # Обработчик GET-запроса
    #-----------------------------------------------------------------------------
    def do_GET(self) -> None:
        '''
        Метод, который обрабатывает GET-запросы на сервер
        При получении GET-запроса возвращаем наполнение запрошенной директории
        (если запрашивается директория). Если запрашивается файл - файл будет скачан

        Не принимает входных параметров

        Ничего не возвращает
        '''
        logging.info(f"GET request,\nPath: {self.path}\nHeaders:\n{self.headers}\n")
        logging.debug(f"Requested path on server: {root_dir}{self.path}")
        path = f'{root_dir}{self.path}'
        if path.endswith('/'):
            path = path[:-1]
        # Если путь существует
        if os.path.exists(path):
            logging.debug(f"{path} exists")
            # Если запрашивается директория
            if os.path.isdir(path):
                logging.debug(f"{path} is directory")
                f = self.list_directory(path)
                if f:
                    logging.debug("Send HTML page with directory content")
                    self.copyfile(f, self.wfile)
                f.close()
                return
            # Если запрашивается файл
            else:
                logging.debug(f"{path} is file")
                f = self.send_file(path)
                if f:
                    logging.debug("Send file")
                    self.copyfile(f, self.wfile)
                f.close()
                return
        # Если путь не существует
        else:
            logging.info(f"{path} does not exist")
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        
    #-----------------------------------------------------------------------------
    # Метод получения файла от клиента
    #-----------------------------------------------------------------------------
    def upload_file(self) -> None:
        '''
        Метод получает отправляемый клиентом файл и сохраняет его в директорию, запрошенную с сервера
        под тем же именем с которым был отправлен

        Не принимает на вход никаких параметров

        Ничего не возвращает
        '''
        logging.warning("Try get file from client")
        # Парсим заголовки пакета
        ctype, pdict = cgi.parse_header(self.headers['Content-Type'])
        boundary = bytes(pdict['boundary'], 'utf-8')
        remainbytes = int(self.headers['content-length'])
        line = self.rfile.readline()
        remainbytes -= len(line)
        if not boundary in line:
            logging.warning("Content NOT begin with boundary")
            self.send_error(HTTPStatus.NOT_FOUND, "Error in upload file")
            return None
        line = self.rfile.readline()
        remainbytes -= len(line)
        filename = re.findall(r'Content-Disposition.*name="datafile"; filename="(.*)"', line.decode('utf-8'))
        if not filename:
            logging.warning("Can't find out file name")
            self.send_error(HTTPStatus.NOT_FOUND, "Error in upload file")
            return None
        path = self.translate_path(self.path)
        filepath = os.path.join(path, filename[0])
        line = self.rfile.readline()
        remainbytes -= len(line)
        line = self.rfile.readline()
        remainbytes -= len(line)
        # Открываем файл на байтовую запись
        logging.debug(f"Try write uploading file data in {filepath}")
        try:
            out = open(filepath, 'wb')
        except IOError:
            logging.warning("Can't create file to write, maybe no permission")
            self.send_error(HTTPStatus.NOT_FOUND, "Error in upload file")
            return None
        # Вычитываем все передаваемые данные и записываем их в файл        
        preline = self.rfile.readline()
        remainbytes -= len(preline)
        while remainbytes > 0:
            line = self.rfile.readline()
            remainbytes -= len(line)
            if boundary in line:
                preline = preline[0:-1]
                if preline.endswith(b'\r'):
                    preline = preline[0:-1]
                out.write(preline)
                out.close()
                return None
            else:
                out.write(preline)
                preline = line
        
        logging.warning("Unexpected end of data")
        self.send_error(HTTPStatus.NOT_FOUND, "Error in upload file")
        return None
    
    #-----------------------------------------------------------------------------
    # Обработчик POST запроса
    #-----------------------------------------------------------------------------
    def do_POST(self) -> None:
        '''
        Метод обрабатывает POST запрос, сохраняет передаваемый файл на сервере под тем же именем, под
        которым он передается

        Не принимает входных параметров

        Ничего не возвращает
        '''
        logging.info(f"POST request,\nPath: {self.path}\nHeaders:\n{self.headers}\n")
        ctype, pdict = cgi.parse_header(self.headers['Content-Type'])
        if ctype == 'multipart/form-data':
            self.upload_file()
        # Возвращаем содержимое директории, чтобы обеспечить непрервную для клиента работу сервера
        path = f'{root_dir}{self.path}'
        f = self.list_directory(path)
        if f:
            self.copyfile(f, self.wfile)
        f.close()


#-----------------------------------------------------------------------------
# Функция запуска сервера
#-----------------------------------------------------------------------------
def run(server_class = HTTPServer, handler_class = Server, address = "", port = 8080, loglevel = "debug", logfile = "HTTPTransfer.log"):
    '''
    Функция отвечает за запуск сервера, принимает параметры для настройки, устанавливает их серверу
    и включает его

    Принимаемые параметры:
    server_class - класс, реализующий сам сервер;
    handler_class - клас, реализующий обработку запросов;
    address - адрес, который будет прослушивать сервер. По умолчанию: 0.0.0.0;
    port - порт, который будет прослушивать сервер. По умолчанию: 8080;
    loglevel - уровень логирования. По умолчанию: debug;
    logfile - файл для сохранения логовю. По умолчанию: HTTPTransfer.log;
    server_dir - абсолютный путь к директории в которой запускается сервер. По умолчанию: текущая рабочая директория;

    Функция ничего не возвращает
    '''
    # Выставляем уровень логирования
    logging_level = {
        'debug': DEBUG,
        'info': INFO,
        'warning': WARNING,
        'error': ERROR
    }
    try:
        logging.basicConfig(level = logging_level.get(loglevel.lower(), DEBUG), filename=logfile, filemode='w')
    except PermissionError:
        print(f"For {logfile} permission dinied")
        quit()
    except Exception  as e:
        print(f'Unexpected error:\n{e}')
        quit()


    server_address = (address, port)
    httpd = server_class(server_address, handler_class)
    logging.info('Starting httpd...\n')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"Unexpected error: \n{e}")
    httpd.server_close()
    logging.info('Stopping httpd...\n')
    quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'Simple HTTP file transfer server. Use for download and upload files')
    parser.add_argument('-b','--BindingAddress', help = 'The address that the server will listen to. Default: 0.0.0.0', type = str, default = '0.0.0.0')
    parser.add_argument('-p','--port', help = 'The port that the server will listen to. Default: 8080', type = int, default = 8080)
    parser.add_argument('-l', '--loglevel', help = 'Log level for server proccess. Default: debug', type = str, default = "debug")
    parser.add_argument('--logfile', help="File to save logs", type=str, default="HTTPTransfer.log")
    parser.add_argument('-d','--ServerDir', help="Absolute path to directory for HTTP server. Default: current worcing directory", type=str, default=None)
    
    args = parser.parse_args()
    address = args.BindingAddress
    port = args.port
    loglevel = args.loglevel
    logfile = args.logfile
    server_dir = args.ServerDir
    
    # Определяемся с корневой директорией
    if server_dir is not None:
        if os.path.exists(server_dir):
            if os.path.isdir(server_dir):
                if server_dir.endswith('/'):
                    server_dir = server_dir[:-1]
                root_dir = server_dir
            else:
                print(f"{server_dir} is not a directory, starting sever in current workind directory")
        else:
            print(f"{server_dir} does not exist, starting sever in current workind directory")

    run(address = address, port = port, loglevel = loglevel, logfile=logfile)

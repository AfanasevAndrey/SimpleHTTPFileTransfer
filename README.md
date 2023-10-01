Простой файлообменник.
Включает на хосте HTTP-сервер, позволяющий передавать файлы от сервера клиенту и от клиента серверу.
Пример запуска и ключей:
```
python SimpleHTTPFileTransfer.py -h

usage: SimpleHTTPFileTransfer.py [-h] [-b BINDINGADDRESS] [-p PORT] [-l LOGLEVEL] [--logfile LOGFILE] [-d SERVERDIR]

Simple HTTP file transfer server. Use for download and upload files

options:
  -h, --help            show this help message and exit
  -b BINDINGADDRESS, --BindingAddress BINDINGADDRESS
                        The address that the server will listen to. Default: 0.0.0.0
  -p PORT, --port PORT  The port that the server will listen to. Default: 8080
  -l LOGLEVEL, --loglevel LOGLEVEL
                        Log level for server proccess. Default: debug
  --logfile LOGFILE     File to save logs
  -d SERVERDIR, --ServerDir SERVERDIR
                        Absolute path to directory for HTTP server. Default: current worcing directory
```
Если явно не указаны директория для сервера, то открывается текущая рабочая директория.
Если явно не указан файл для сохранения лога, то лог сохраняется в текущую рабочую директорию.
Если явно не указаны адрес и порт сервера, то он будет слушать 0.0.0.0:8080

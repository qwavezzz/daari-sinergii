# Отдельный вход по SSH-ключу: Windows → VPS

**Не выполнять в текущем этапе.** Пользователь решил сохранить вход на VPS по
логину и паролю. Ниже остаётся необязательная справочная инструкция для возможного
будущего перехода; создание dariadmin и отключение парольного входа не требуются.

Сейчас VPS разрешает root-вход по паролю. Первый этап — добавить проверенный
административный вход по ключу. Существующее подключение Remote Explorer оставить
открытым до проверки нового. На этом этапе SSH-конфигурация и firewall не меняются.
Проверить, что доступна аварийная консоль VPS в REG.RU.

Это доступ разработчика/системного администратора. Для ежедневного редактирования
сайта клиент пользуется Django-админкой. Каждому техническому пользователю нужен
отдельный ключ; приватный ключ разработчика клиенту не передаётся.

## 1. Создать ключ на своём Windows-компьютере

Открыть **отдельный локальный PowerShell** через меню «Пуск», не терминал Ubuntu
в Remote Explorer. Выполнить:

```powershell
$dariKey = Join-Path $env:USERPROFILE '.ssh\dari_admin_ed25519'
New-Item -ItemType Directory -Path (Split-Path -Parent $dariKey) -Force | Out-Null
if ((Test-Path -LiteralPath $dariKey) -or (Test-Path -LiteralPath "$dariKey.pub")) {
    throw 'Файл ключа уже существует. Существующий ключ не перезаписывать.'
} else {
    ssh-keygen -t ed25519 -a 64 -f $dariKey -C 'dari-vps-admin'
}
```

На `Enter passphrase` задать парольную фразу ключа и повторить её. При вводе
символы могут не отображаться. Сохранить фразу и резервную копию ключа в защищённом
хранилище. Это новый локальный секрет, не пароль от VPS.

Если `ssh-keygen` завершился успешно, показать **публичную** часть:

```powershell
Get-Content -LiteralPath "$env:USERPROFILE\.ssh\dari_admin_ed25519.pub"
```

Скопировать всю одну строку, начинающуюся с `ssh-ed25519`. Файл без `.pub`
остаётся на компьютере: его не вставлять в чат, на VPS или в проект.

## 2. Добавить отдельного администратора на VPS

Вернуться в существующее SSH-подключение Remote Explorer. В терминале **Ubuntu**:

```bash
sudo adduser dariadmin
```

Задать отдельный пароль пользователя — он понадобится для `sudo`. Поля ФИО и
телефонов можно оставить пустыми. Если команда сообщает, что пользователь уже
существует, сначала выяснить, кому он принадлежит; не назначать ему права вслепую.
Имя `dari` не использовать: это существующая учётная запись веб-приложения.

После успешного создания пользователя:

```bash
sudo usermod -aG sudo dariadmin
sudo install -d -m 0700 -o dariadmin -g dariadmin /home/dariadmin/.ssh
sudo nano /home/dariadmin/.ssh/authorized_keys
```

Вставить публичную строку `ssh-ed25519 …`, сохранить `Ctrl+O`, `Enter`, выйти
`Ctrl+X`. Затем:

```bash
sudo chown dariadmin:dariadmin /home/dariadmin/.ssh/authorized_keys
sudo chmod 0600 /home/dariadmin/.ssh/authorized_keys
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Последняя команда показывает публичный отпечаток **сервера** — он нужен для
проверки при первом подключении с компьютера. Пароли и приватные ключи не выводятся.

## 3. Проверить новый вход из второго окна

В **локальном Windows PowerShell**, оставив старое подключение открытым:

```powershell
ssh -o HostKeyAlgorithms=ssh-ed25519 -o IdentitiesOnly=yes -o PreferredAuthentications=publickey -o PasswordAuthentication=no -i "$env:USERPROFILE\.ssh\dari_admin_ed25519" dariadmin@134.0.113.203
```

Если появится запрос доверия серверу, сравнить его SHA256-отпечаток с предыдущим
шагом и подтвердить только совпадающий. Запрос `Enter passphrase for key` —
парольная фраза локального ключа. В этой проверке вход по паролю VPS отключён
только для клиентской команды, чтобы успешный вход действительно подтверждал ключ.

Уже в новом серверном сеансе:

```bash
whoami
sudo -v
sudo id -u
```

Ожидается `dariadmin`, успешный `sudo -v` и `0`. Для sudo вводится пароль
пользователя `dariadmin`, заданный при создании; символы не отображаются.
Если вход или sudo не работает, исправить этот этап через оставленное старое
подключение. Действующий способ входа пока сохраняется.

## 4. Добавить вход в Remote Explorer

В **локальном** файле `%USERPROFILE%\.ssh\config` добавить блок, сохранив
существующие подключения:

```sshconfig
Host dari-vps-admin
    HostName 134.0.113.203
    User dariadmin
    IdentityFile ~/.ssh/dari_admin_ed25519
    IdentitiesOnly yes
```

Открыть `dari-vps-admin` через Remote Explorer в **новом окне** и проверить вход.
Системные файлы обслуживаются через `sudo`; изменение SSH-учётной записи не меняет
владельцев сайта, базы, файлов `/etc/dari` или права Django-админки.

После успешной проверки сообщить только результаты `whoami`, `sudo id -u` и
удалось ли подключиться через Remote Explorer. Сам ключ или пароль присылать не нужно.
Следующий этап — запрет прямого root/парольного входа и настройка UFW с сохранением
SSH 22, HTTP 80 и HTTPS 443. Он выполняется после подтверждения нового доступа.

Основание: [SSH-ключи на Windows — Microsoft](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement),
[OpenSSH в Ubuntu](https://ubuntu.com/server/docs/how-to/security/openssh-server/).

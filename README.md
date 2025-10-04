# Telegram WebApp WebRTC MVP (Python)
This is a lightweight app for video calls between Telegram users, powered by WebRTC. It works as a Telegram Web App and is integrated with a Telegram bot that helps invite users into the service's private network.

Currently at the MVP stage, but functional.


## Install

### Hosting
For web app part you need configure some domain. Example of nginx config with proxy pass to another server^
```conf
    server {
        server_name  tgringer.domain.tld;
        listen       80;
        access_log   /var/log/nginx/tgringer-access.log  main;
        error_log   /var/log/nginx/tgringer-error.log;
        location / {
        proxy_pass      http://192.168.7.3:91;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_connect_timeout       600;
        proxy_send_timeout          600;
        proxy_read_timeout          600;
        send_timeout                600;
        }

	}
```
Also configure HTTPS. For example via letsencrypt (choose option 2).


### Backend
```bash
cd /var/www
git clone https://github.com/sphynkx/tgringer
cd tgringer
cp intall/.env.example .env
```
Go to BotFather, run `/newbot` set bot name and bot username. receive token. Then modify `.env` - set this token to `BOT_TOKEN` variable. Also set previously configured hostname to `APP_BASE_URL`.

Install venv and all necessary modules:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
```


### Database
Copy sample to `.sql`, modify it (set DB name, user name, password) and run:
```
cp install/grant-priv.sql-sample grant-priv.sql
mysql -u root -p < grant-priv.sql
rm -f grant-priv.sql
```

Install scheme (use real username and db name if they were modified):
```
mysql -u root -p tgringer < install/schema.sql
```


### Network
Modify (if need) systemd files `install/tgringer-*.service`, copy them, enable and run:
```bash
cp install/tgringer-*.service /etc/systemd/system
systemctl daemon-reload
systemctl enable tgringer-app
systemctl enable tgringer-bot
systemctl start tgringer-app
systemctl start tgringer-bot

```

### Check
Run from external side:
```bash
curl https://tgringer.domain.tld/health
```
You may receive:
```json
{
	"ok":true
}
```
Open Telegram client, find bot via bot name (as configured in BotFather), start it. Bot could send welcome message. 

Send command `/newcall`. You receive links for web-app and browser. Open one of them. Press "Join" button and allow microphone and camera. 


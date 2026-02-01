# Deployment Guide - Singapore Trip Planner

## Option 1: Streamlit Cloud (Recommended - Free & Easy)

### Prerequisites
1. Push your code to GitHub
2. Create a Streamlit Cloud account at https://streamlit.io/cloud

### Steps:

1. **Prepare Your Repository**
   ```bash
   # Create requirements.txt if not already present
   pip freeze > requirements.txt
   
   # Make sure these files are in your repo root:
   # - streamlit_app.py
   # - requirements.txt
   # - app/ (folder with all backend code)
   # - data/ (folder with docs)
   # - static/ (folder with images)
   ```

2. **Create `.streamlit/secrets.toml` (for local testing)**
   ```toml
   OPENAI_API_KEY = "your-key-here"
   ```

3. **Add `.gitignore` to avoid committing secrets**
   ```
   .streamlit/secrets.toml
   __pycache__/
   *.pyc
   .env
   ```

4. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/your-username/singapore-trip-planner.git
   git push -u origin main
   ```

5. **Deploy on Streamlit Cloud**
   - Go to https://share.streamlit.io/
   - Click "New app"
   - Select your GitHub repository
   - Set main file path: `streamlit_app.py`
   - Click "Advanced settings" → "Secrets"
   - Add your secrets:
     ```toml
     OPENAI_API_KEY = "your-actual-key"
     ```
   - Click "Deploy"

6. **Start the FastAPI Backend Separately**
   
   Note: Streamlit Cloud can only run the Streamlit frontend. You need to deploy the FastAPI backend separately.

### Option for Backend Deployment:

#### Render.com (Free tier available)

1. Create `render.yaml` in project root:
   ```yaml
   services:
     - type: web
       name: singapore-trip-api
       env: python
       buildCommand: pip install -r requirements.txt
       startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
       envVars:
         - key: OPENAI_API_KEY
           sync: false
   ```

2. Push to GitHub

3. Go to https://render.com, create account, and connect your GitHub repo

4. Add environment variables in Render dashboard:
   - `OPENAI_API_KEY`
   - `OPENAI_TIMEOUT_SECONDS=300`

5. Get your backend URL (e.g., `https://singapore-trip-api.onrender.com`)

6. Update Streamlit secrets with backend URL:
   ```toml
   OPENAI_API_KEY = "your-key"
   API_BASE_URL = "https://singapore-trip-api.onrender.com"
   ```

---

## Option 2: Single Server Deployment (VPS/EC2)

### Prerequisites
- Ubuntu/Debian server with public IP
- Domain name (optional)

### Steps:

1. **Install Dependencies**
   ```bash
   sudo apt update
   sudo apt install python3-pip python3-venv nginx
   ```

2. **Clone Repository**
   ```bash
   cd /var/www
   git clone https://github.com/your-username/singapore-trip-planner.git
   cd singapore-trip-planner
   ```

3. **Set Up Python Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Create Environment Variables**
   ```bash
   # Create .env file
   cat > .env << EOF
   OPENAI_API_KEY=your-key-here
   API_BASE_URL=http://localhost:8000
   OPENAI_TIMEOUT_SECONDS=300
   API_TIMEOUT_SECONDS=300
   EOF
   ```

5. **Set Up Systemd Service for FastAPI**
   ```bash
   sudo nano /etc/systemd/system/trip-api.service
   ```
   
   Add:
   ```ini
   [Unit]
   Description=Singapore Trip Planner API
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/var/www/singapore-trip-planner
   Environment="PATH=/var/www/singapore-trip-planner/venv/bin"
   EnvironmentFile=/var/www/singapore-trip-planner/.env
   ExecStart=/var/www/singapore-trip-planner/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

   [Install]
   WantedBy=multi-user.target
   ```

6. **Set Up Systemd Service for Streamlit**
   ```bash
   sudo nano /etc/systemd/system/trip-frontend.service
   ```
   
   Add:
   ```ini
   [Unit]
   Description=Singapore Trip Planner Frontend
   After=network.target trip-api.service

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/var/www/singapore-trip-planner
   Environment="PATH=/var/www/singapore-trip-planner/venv/bin"
   EnvironmentFile=/var/www/singapore-trip-planner/.env
   ExecStart=/var/www/singapore-trip-planner/venv/bin/streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0

   [Install]
   WantedBy=multi-user.target
   ```

7. **Start Services**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start trip-api
   sudo systemctl start trip-frontend
   sudo systemctl enable trip-api
   sudo systemctl enable trip-frontend
   ```

8. **Configure Nginx as Reverse Proxy**
   ```bash
   sudo nano /etc/nginx/sites-available/trip-planner
   ```
   
   Add:
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://localhost:8501;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_cache_bypass $http_upgrade;
       }

       location /api {
           proxy_pass http://localhost:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

9. **Enable Site and Restart Nginx**
   ```bash
   sudo ln -s /etc/nginx/sites-available/trip-planner /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

10. **Access Your App**
    - Visit `http://your-domain.com` or `http://your-server-ip`

---

## Environment Variables Summary

### Required:
- `OPENAI_API_KEY` - Your OpenAI API key

### Optional:
- `API_BASE_URL` - Backend URL (default: http://localhost:8000)
- `OPENAI_TIMEOUT_SECONDS` - Timeout for OpenAI calls (default: 180)
- `API_TIMEOUT_SECONDS` - Timeout for frontend API calls (default: 300)

---

## Cost Considerations

- **Streamlit Cloud**: Free tier available (1 private app)
- **Render.com**: Free tier available (with cold starts)
- **VPS (DigitalOcean/Linode)**: ~$5-10/month
- **AWS EC2 t2.micro**: Free tier for 1 year, then ~$8/month
- **OpenAI API costs**: Pay per use (depends on trip complexity)

---

## Monitoring & Maintenance

1. **Check Logs**
   ```bash
   # FastAPI logs
   sudo journalctl -u trip-api -f
   
   # Streamlit logs
   sudo journalctl -u trip-frontend -f
   ```

2. **Update Application**
   ```bash
   cd /var/www/singapore-trip-planner
   git pull
   sudo systemctl restart trip-api
   sudo systemctl restart trip-frontend
   ```

3. **Monitor OpenAI Usage**
   - Check https://platform.openai.com/usage
   - Set usage limits to avoid unexpected costs

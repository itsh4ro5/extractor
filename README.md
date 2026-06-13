---
title: Extractor
emoji: 🚀
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
---

# 🚀 Classplus Extractor Bot

A powerful, fully asynchronous Telegram bot designed to extract purchased course contents from the Classplus platform. Built with `python-telegram-bot` and `aiohttp`, it offers blazing fast performance and a non-blocking architecture.

## ✨ Features
* **Dual Login System:** Supports both OTP-based login (Email & Mobile) and direct Token login.
* **Interactive UI:** Clean inline-button navigation for a seamless user experience.
* **Fast Extraction:** Asynchronous recursive fetching prevents API timeouts and handles large courses efficiently.
* **Smart Rate Limiting:** Built-in delays to avoid IP bans and server blocks.
* **Database Integration:** Uses MongoDB to securely store user sessions and tokens.
* **Cloud Ready:** Pre-configured with a Flask health-check endpoint (Port 7860) making it 100% compatible with Hugging Face Spaces, Koyeb, Render, and Heroku.

---

## 🛠️ Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Show the interactive welcome menu. |
| `/login cp <orgCode> <mobile>` | Initiate OTP login (Mobile or Email). |
| `/login cp <token>` | Login directly using an Auth Token. |
| `/courses cp` | Fetch and display a list of all purchased courses. |
| `/extract cp <courseId>` | Extract course videos, PDFs, and notes into a TXT file. |

---

## ⚙️ Environment Variables (Secrets)

Before deploying the bot, you **MUST** set the following environment variables. Without these, the bot will crash immediately upon startup.

* `BOT_TOKEN` : Your Telegram Bot Token (Get it from [@BotFather](https://t.me/BotFather) on Telegram).
* `MONGO_URI` : Your MongoDB connection string (e.g., `mongodb+srv://<user>:<password>@cluster.mongodb.net/...`).

---

## 🚀 Deployment Guide (Hugging Face Spaces)

This repository is highly optimized for deployment on **Hugging Face Spaces** using Docker.

### Step 1: Add Secrets in HF
1. Go to your Space's **Settings** tab.
2. Scroll down to the **Variables and secrets** section.
3. Add a new secret with Name: `BOT_TOKEN` and your Telegram token as the value.
4. Add another secret with Name: `MONGO_URI` and your MongoDB connection URL as the value.

### Step 2: Upload Code
Upload the code to your space (`bot.py`, `Dockerfile`, `requirements.txt`, and the `apps/`, `core/` folders). Thanks to the metadata block at the top of this file, Hugging Face will automatically detect the Docker SDK and run your bot on port `7860`.

---

## 🛡️ Anti-Sleep Configuration (For Free Tiers)
If you are deploying on a free tier (like HF Free Spaces), your bot might go to sleep after some inactivity. To prevent this:
1. Copy your Space's direct URL (e.g., `https://your-username-your-space-name.hf.space`).
2. Go to a free ping service like [cron-job.org](https://cron-job.org/) or [UptimeRobot](https://uptimerobot.com/).
3. Setup a cron job to ping your URL every 10-15 minutes. 

---

## 📝 Disclaimer
This tool is for educational and personal archiving purposes only. Do not use this to distribute copyrighted materials.

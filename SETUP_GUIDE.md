# PGP Container Glass Intelligence Platform — Windows Setup & Scheduling Guide

This guide describes how to deploy and automate the **PGP Container Glass Daily Intelligence Platform** on a Windows Enterprise PC. Following these steps will enable automatic Daily RSS Scraping, Gemini AI relevance filtering/summarization, and professional HTML/Excel report deliveries directly to your inbox every morning.

---

## Prerequisites
Before beginning, make sure you have:
* An active internet connection.
* A Gemini API key (see [Step 5](#step-5-configure-the-env-file) below).
* A Gmail account with 2-Step Verification enabled to act as the sender.

---

## Step-by-Step Deployment Guide

### Step 1: Install Python
1. Download Python 3.11 or later for Windows (e.g., Python 3.11.x or Python 3.12.x) from the official website:
   👉 **[https://www.python.org/downloads/](https://www.python.org/downloads/)**
2. Run the installer.
3. ⚠️ **IMPORTANT**: On the first screen of the installer, check the box that says **"Add python.exe to PATH"** at the bottom. This is required for the setup scripts to detect Python.
4. Click **Install Now** and complete the installation.

### Step 2: Copy the Project Folder
Copy the entire `PGP glass news automation` folder onto the target Windows PC (e.g., in `C:\PGP-Container-Glass-Intelligence` or a similar folder).

### Step 3: Open Command Prompt
1. Press the **Windows Key** on your keyboard, type `cmd`, and press Enter.
2. Navigate to your project folder using `cd`. For example:
   ```cmd
   cd /d C:\PGP-Container-Glass-Intelligence
   ```

### Step 4: Run setup.bat
1. Run the setup script in the Command Prompt or double-click it in Windows Explorer:
   ```cmd
   setup.bat
   ```
2. The setup script will:
   * Create a python virtual environment (`.venv`) to keep dependencies isolated.
   * Upgrade `pip` to the latest version.
   * Install all required packages (`requests`, `beautifulsoup4`, `feedparser`, etc.).
   * Create a `.env` file from the example if one is missing.
   * Execute `check_system.py` to run pre-flight diagnostics.
3. Keep the prompt open to confirm all packages installed correctly.

### Step 5: Configure the .env File
Open the newly created `.env` file in the root folder with a text editor (like Notepad) and fill in the required fields:

```env
# Gmail sender account credentials
GMAIL_USER=your_sender_account@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Comma-separated list of email recipients
RECIPIENTS=recipient1@example.com,recipient2@example.com

# Gemini 2.5 Flash API Key
GEMINI_API_KEY=your_gemini_api_key_here
```

> 💡 **How to get a Gmail App Password:**
> 1. Go to your **Google Account settings** -> **Security**.
> 2. Enable **2-Step Verification** (if not already enabled).
> 3. Go to **2-Step Verification** page, scroll to the bottom, and select **App Passwords**.
> 4. Choose **Mail** as the app and **Windows Computer** as the device, then click **Generate**.
> 5. Copy the 16-character passcode and paste it into the `GMAIL_APP_PASSWORD` field in `.env`.

> 💡 **How to get a Gemini API Key:**
> 1. Visit the Google AI Studio page: **[https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)**.
> 2. Create a free API Key and paste it into the `GEMINI_API_KEY` field in `.env`.

### Step 6: Test Manual Run
1. Double-click the `run.bat` file in the project folder.
2. The launcher will automatically find Python, activate the virtual environment, execute the orchestrator (`main.py`), and display output in the Command Prompt window.
3. If run manually, the window will pause at the end showing a success/failure message.

### Step 7: Verify Email Delivery
* Check the recipient inboxes configured in your `.env`.
* You should receive a professional HTML email summary with an attached Excel workbook containing the scraped, relevant container glass news articles.
* Check the `logs` folder inside the project directory. You should see a file named `YYYY-MM-DD_HH-MM-SS.log` containing all the execution details and the final `EXECUTION SUMMARY` block.

---

## Step 8: Configure Windows Task Scheduler
To run the platform automatically every morning at 9:00 AM:

1. Press the **Windows Key**, type `Task Scheduler`, and press Enter.
2. In the right pane under **Actions**, click **Create Basic Task...**
3. **Name**: `PGP Container Glass Intelligence`
4. **Trigger**: Select **Daily**, then click Next.
5. **Daily**:
   * Set the Start Time to **9:00:00 AM**.
   * Recur every: **1** days. Click Next.
6. **Action**: Select **Start a program**, then click Next.
7. **Start a Program**:
   * **Program/script**: Click Browse and select `run.bat` from your project folder.
   * **Start in (optional)**: ⚠️ **CRITICAL**: Copy the absolute path to your project folder (e.g., `C:\PGP-Container-Glass-Intelligence`) and paste it here. **Do not put quotes around the path.** If this is left empty, the script will fail to locate your configuration and JSON files.
   * Click Next, then click **Finish**.
8. **Configure Advanced Settings**:
   * Double-click the newly created task `PGP Container Glass Intelligence` in the Task Scheduler Library list.
   * In the **General** tab:
     * Select **Run whether user is logged on or not**.
     * Check **Run with highest privileges** (avoids user permission issues).
   * In the **Conditions** tab:
     * Check **Wake the computer to run this task** (ensures execution if the PC is sleeping).
   * In the **Settings** tab:
     * Check **If the task fails, restart every**: Set to **5 minutes** and attempt up to **3 times**.
     * Check **Stop the task if it runs longer than**: Set to **30 minutes** (prevents hung processes).
     * Click OK. It may ask you to input your Windows Account Password to save these settings.

---

### Step 9: Test Scheduled Task
1. In the Task Scheduler Library, locate your `PGP Container Glass Intelligence` task.
2. Right-click the task and click **Run**.
3. The task state will change to "Running" in the background (no cmd window will pop up because it is running in background service mode).

### Step 10: Verify Logs and Email
1. Check the `logs/` directory in the project folder. A new log file `YYYY-MM-DD_HH-MM-SS.log` should have been generated.
2. Open the file and scroll to the bottom to verify that it ends with a success status:
   ```text
   ============================================================
   EXECUTION SUMMARY
   ============================================================
   Start Time:        2026-07-01 09:00:02
   End Time:          2026-07-01 09:02:14
   Execution Time:    132.4 seconds
   Articles Scraped:  142
   Relevant Articles: 3
   Email Status:      Success
   Errors:            None
   Exit Code:         0
   ============================================================
   ```
3. Confirm that the report email was successfully delivered.

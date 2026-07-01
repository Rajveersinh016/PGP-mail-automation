#!/usr/bin/env python
"""
check_system.py — Diagnostic check for PGP Container Glass Intelligence Platform.
Verifies all prerequisites for Windows enterprise deployment and prints PASS/FAIL.
"""

import sys
import os
import smtplib
import ssl
from pathlib import Path

# Try to import requests for Gemini/Internet checks
try:
    import requests
except ImportError:
    requests = None

# IST timezone helper
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))

def load_env():
    """Load env variables from .env or .env.example without overwriting existing environment."""
    for filename in (".env", ".env.example"):
        path = Path(__file__).parent / filename
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key and key not in os.environ:
                        os.environ[key] = val
            except Exception:
                pass

def main():
    load_env()
    print("============================================================")
    print("  PGP Container Glass Platform Diagnostics & System Verification")
    print("============================================================")
    
    results = {}
    
    # 1. Python Version
    ver = sys.version_info
    ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    if ver >= (3, 11):
        results["Python Version (>= 3.11)"] = (True, f"PASS (Python {ver_str})")
    else:
        results["Python Version (>= 3.11)"] = (False, f"FAIL (Python {ver_str} is older than 3.11)")

    # 2. Required Packages Check
    packages = {
        "feedparser": "feedparser",
        "beautifulsoup4": "bs4",
        "requests": "requests",
        "lxml": "lxml",
        "openpyxl": "openpyxl",
        "python-dateutil": "dateutil"
    }
    missing_pkgs = []
    for pkg_name, import_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_pkgs.append(pkg_name)
            
    if not missing_pkgs:
        results["Required Packages Check"] = (True, "PASS (All required packages installed)")
    else:
        results["Required Packages Check"] = (False, f"FAIL (Missing: {', '.join(missing_pkgs)})")

    # 3. Required Folders Check
    folders = ["logs", "reports", "temp", "output", "data"]
    missing_folders = []
    project_dir = Path(__file__).parent
    for folder in folders:
        if not (project_dir / folder).is_dir():
            missing_folders.append(folder)
            
    if not missing_folders:
        results["Required Folders Exist"] = (True, "PASS (All required directories present)")
    else:
        results["Required Folders Exist"] = (False, f"FAIL (Missing directories: {', '.join(missing_folders)})")

    # 4. Required Files Check
    files = [
        "main.py",
        "scraper.py",
        "email_service.py",
        "reporter.py",
        "gemini.py",
        "deduplicator.py",
        "requirements.txt",
        ".env",
        "data/watchlist.json",
        "data/keywords.json",
        "data/sources.json",
        "data/companies.json",
        "data/india_locations.json"
    ]
    missing_files = []
    for f in files:
        if not (project_dir / f).exists():
            missing_files.append(f)
            
    if not missing_files:
        results["Required Files Exist"] = (True, "PASS (All core files and configurations present)")
    else:
        results["Required Files Exist"] = (False, f"FAIL (Missing files: {', '.join(missing_files)})")

    # 5. Disk Write & Read Permissions Check
    write_failed_folders = []
    all_folders = ["."] + folders
    for folder in all_folders:
        path = project_dir / folder
        if not path.exists():
            continue
        test_file = path / ".diagnostics_write_test"
        try:
            test_file.write_text("write_test_data", encoding="utf-8")
            content = test_file.read_text(encoding="utf-8")
            if content != "write_test_data":
                raise ValueError("Read content mismatch")
            test_file.unlink()
        except Exception as e:
            write_failed_folders.append(f"{folder} ({str(e)})")
            
    if not write_failed_folders:
        results["Disk Write Permissions"] = (True, "PASS (Successfully verified write permissions)")
    else:
        results["Disk Write Permissions"] = (False, f"FAIL (Write errors in: {', '.join(write_failed_folders)})")

    # 6. Internet Connectivity Check
    if requests is None:
        results["Internet Connectivity"] = (False, "FAIL (Cannot verify - 'requests' package not installed)")
    else:
        try:
            resp = requests.get("https://news.google.com", timeout=6)
            if resp.status_code == 200:
                results["Internet Connectivity"] = (True, "PASS (Connected to the Internet)")
            else:
                results["Internet Connectivity"] = (False, f"FAIL (Reachable but returned HTTP {resp.status_code})")
        except Exception as e:
            results["Internet Connectivity"] = (False, f"FAIL (Connection error: {e})")

    # 7. Gemini API Connection Check
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        results["Gemini API Key Check"] = (False, "FAIL (GEMINI_API_KEY is not configured in .env)")
        results["Gemini API Connection"] = (False, "FAIL (Cannot run API call without a valid key)")
    elif requests is None:
        results["Gemini API Key Check"] = (True, "PASS (GEMINI_API_KEY is set)")
        results["Gemini API Connection"] = (False, "FAIL (Cannot verify - 'requests' package not installed)")
    else:
        results["Gemini API Key Check"] = (True, "PASS (GEMINI_API_KEY is set)")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            if resp.status_code == 200:
                results["Gemini API Connection"] = (True, "PASS (Successfully connected and verified key)")
            else:
                results["Gemini API Connection"] = (False, f"FAIL (API error code {resp.status_code}: {resp.text.strip()[:100]}...)")
        except Exception as e:
            results["Gemini API Connection"] = (False, f"FAIL (API connection error: {e})")

    # 8. SMTP Credentials and Authentication Check
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    recipients = os.environ.get("RECIPIENTS", "").strip()
    
    if not gmail_user or gmail_user == "your_gmail_sender@gmail.com":
        results["SMTP Credentials Check"] = (False, "FAIL (GMAIL_USER is not configured in .env)")
        results["SMTP Authentication Check"] = (False, "FAIL (Cannot authenticate without user)")
    elif not gmail_pass or gmail_pass == "your_gmail_app_password_here":
        results["SMTP Credentials Check"] = (False, "FAIL (GMAIL_APP_PASSWORD is not configured in .env)")
        results["SMTP Authentication Check"] = (False, "FAIL (Cannot authenticate without app password)")
    elif not recipients or recipients == "recipient1@example.com,recipient2@example.com":
        results["SMTP Credentials Check"] = (False, "FAIL (RECIPIENTS list has placeholder values or is missing)")
        results["SMTP Authentication Check"] = (False, "FAIL (Skipped due to placeholder recipients)")
    else:
        results["SMTP Credentials Check"] = (True, "PASS (Credentials set in .env)")
        
        SMTP_HOST = "smtp.gmail.com"
        context = ssl.create_default_context()
        connected = False
        smtp_errors = []
        
        try:
            server = smtplib.SMTP(SMTP_HOST, 587, timeout=10)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(gmail_user, gmail_pass)
            server.quit()
            connected = True
            results["SMTP Authentication Check"] = (True, "PASS (Authenticated successfully via Port 587)")
        except Exception as e587:
            smtp_errors.append(f"Port 587: {e587}")
            
        if not connected:
            try:
                server = smtplib.SMTP_SSL(SMTP_HOST, 465, context=context, timeout=10)
                server.login(gmail_user, gmail_pass)
                server.quit()
                results["SMTP Authentication Check"] = (True, "PASS (Authenticated successfully via Port 465)")
                connected = True
            except Exception as e465:
                smtp_errors.append(f"Port 465: {e465}")
                
        if not connected:
            results["SMTP Authentication Check"] = (False, f"FAIL ({' | '.join(smtp_errors)})")

    # Print summary table
    print(f"\n{'Test Name':<35} | Status")
    print("-" * 55)
    
    all_passed = True
    for test_name, (status, message) in results.items():
        print(f"{test_name:<35} | {message}")
        if not status:
            all_passed = False
            
    print("============================================================")
    if all_passed:
        print("OVERALL DIAGNOSTIC RESULT: PASS")
        print("Your system is fully configured and ready for production runs.")
        print("============================================================")
        sys.exit(0)
    else:
        print("OVERALL DIAGNOSTIC RESULT: FAIL")
        print("Please resolve the failures listed above.")
        print("============================================================")
        sys.exit(1)

if __name__ == "__main__":
    main()

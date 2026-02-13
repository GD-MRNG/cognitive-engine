# Discord Notification Guide

This guide explains how to set up and configure the **Discord Notification System** for the research pipeline. This system allows the pipeline to send real-time alerts to your phone or desktop, specifically for **Human-in-the-Loop (HITL)** interventions or critical completion updates.

---

## 1. Setup & Keys

### A. Create the Webhook (The "Mailbox")

1. Open Discord and go to your private server (or create a new one).
2. Right-click the text channel you want alerts in (e.g., `#general`) and select **Edit Channel** (Gear Icon).
3. Go to **Integrations** → **Webhooks**.
4. Click **New Webhook**.
5. **Name it:** (e.g., "Research Bot").
6. **Copy Webhook URL:** This is your `DISCORD_WEBHOOK_URL`.

### B. Get Your User ID (The "Pager")

*This is optional but required if you want the bot to **ping** you (make your phone vibrate).*

1. Go to **User Settings** (Gear Icon, bottom left) → **Advanced**.
2. Toggle **Developer Mode** to **ON**.
3. Close settings.
4. Right-click your own username in any chat or the member list.
5. Click **Copy User ID**. This is your `DISCORD_USER_ID`.

---

## 2. Configuration

Add the keys to your `.env` file in the project root.

```bash
# .env file

# Required: The link to the channel
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/123456/abcdef..."

# Optional: Your numeric ID for pings (leave blank to disable pings)
DISCORD_USER_ID="123456789012345678"

```

---

## 3. Usage in Pipeline (YAML)

You can insert a notification step anywhere in your `workflows/*.yaml` file using the `NotificationTask`.

### Parameters

* **`message`**: The text to display.
* **`level`**: Controls the formatting and urgency.
* `info`: Standard log (ℹ️).
* `success`: Green checkmark (✅).
* `warning`: Warning sign (⚠️).
* `error`: Red siren (🚨).
* `hitl`: **Pings User**. Used for manual intervention requests (🛑).



### Example YAML Configuration

```yaml
steps:
  # ... previous steps ...

  # Example 1: Notify when a long scrape finishes
  - id: "notify_scrape_complete"
    type: "NotificationTask"
    config:
      message: "Scraping phase finished. Starting analysis..."
      level: "info"

  # Example 2: Notify when the entire pipeline is done (Success)
  - id: "notify_pipeline_success"
    type: "NotificationTask"
    config:
      message: "Research Report Generated Successfully!"
      level: "success"

```

---

## 4. Best Practices

1. **Don't Over-Notify:** Only add notifications for "Long Running" boundaries (e.g., after scraping 100 items) or "Terminal States" (Success/Failure).
2. **Reserve `hitl` for Blockers:** Only use the `hitl` level when the pipeline **stops and waits** for you (e.g., `ManualReviewTask`). Using it for info logs will desensitize you to the alerts.
3. **Security:** Never commit your Webhook URL to GitHub. Treat it like a password. If leaked, anyone can spam your channel.

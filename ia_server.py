"""
IA AI Solutions — Business Intake Server
File: ia_server.py

Dedicated server for IA AI Solutions website.
Handles the website chatbot conversations and lead intake emails.

Environment variables (set on Render):
  ANTHROPIC_API_KEY    — from console.anthropic.com
  EMAIL_SENDER         — noreply@ia-aisolutions.com (or Gmail)
  EMAIL_PASSWORD       — Zoho App Password or Gmail App Password
  EMAIL_RECIPIENT      — ismail@ia-aisolutions.com

Render service name: ia-ai-intake
Render start command: gunicorn ia_server:app

Routes:
  POST /chat        — AI conversation (website chatbot)
  POST /ia-intake   — Send lead email with action plan to Ismail
  GET  /health      — Server health check
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import os, smtplib, random
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)
CORS(app)

# ── CONFIG ────────────────────────────────────────────────────────────────────
client          = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
EMAIL_SENDER    = os.environ.get("EMAIL_SENDER", "")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "ismail@ia-aisolutions.com")

# ── SERVICES PRICING (SAR) ────────────────────────────────────────────────────
SERVICES_PRICING = {
    "intake":   {"name":"AI Intake Chatbot",        "setup":1875,  "monthly":562},
    "voice":    {"name":"AI Voice Receptionist",     "setup":3000,  "monthly":750},
    "leads":    {"name":"AI Lead Qualifier",         "setup":1500,  "monthly":562},
    "hr":       {"name":"AI HR Screener",            "setup":1125,  "monthly":450},
    "support":  {"name":"AI Customer Support",       "setup":1312,  "monthly":562},
    "docs":     {"name":"AI Document Processor",     "setup":1500,  "monthly":562},
    "payments": {"name":"AI Payment Reminders",      "setup":750,   "monthly":375},
    "market":   {"name":"AI Market Intelligence",    "setup":1125,  "monthly":750},
    "whatsapp": {"name":"WhatsApp Campaigns",        "setup":938,   "monthly":750},
    "pa":       {"name":"AI Personal Assistant",     "setup":1500,  "monthly":562},
}

# ── ACTION PLAN GENERATOR ─────────────────────────────────────────────────────
def generate_action_plan(intake):
    """Recommend services based on what the lead said and calculate pricing."""
    challenge = (intake.get("challenge","") or intake.get("sum","")).lower()
    area      = intake.get("area","").lower()
    org       = intake.get("org","Unknown business")
    name      = intake.get("name","the client")
    contact   = intake.get("contact","—")
    city      = intake.get("city","KSA")
    staff     = intake.get("staff","—")
    revenue   = intake.get("revenue","—")

    recommended = []
    reasons     = []

    # Intake chatbot — always recommend
    recommended.append("intake")
    reasons.append("Every business loses enquiries after hours — this solves it immediately")

    if any(w in challenge for w in ["call","phone","receiv","voic","ring","answer"]):
        recommended.append("voice")
        reasons.append("Client mentioned phone/call issues — voice receptionist directly addresses this")

    if any(w in challenge for w in ["lead","sale","prospect","client","customer","enquir","inquiry"]):
        recommended.append("leads")
        reasons.append("Client mentioned lead or sales challenges — qualifier delivers ranked leads daily")

    if any(w in challenge for w in ["support","complain","question","query","follow","service"]):
        recommended.append("support")
        reasons.append("Client mentioned customer service overhead — support bot handles 80% automatically")

    if any(w in challenge for w in ["invoice","payment","collect","overdue","owe","bill","cash"]):
        recommended.append("payments")
        reasons.append("Client mentioned payment/collection issues — reminder sequences recover cash faster")

    if any(w in challenge for w in ["document","paper","form","data","entry","manual","process"]):
        recommended.append("docs")
        reasons.append("Client mentioned manual document work — processor eliminates data entry entirely")

    if any(w in challenge for w in ["hire","recruit","staff","team","cv","applicant","interview"]):
        recommended.append("hr")
        reasons.append("Client mentioned hiring/staffing — HR screener cuts screening time by 80%")

    if any(w in area for w in ["real estate","property","agent","letting"]) and "leads" not in recommended:
        recommended.append("leads")
        reasons.append("Real estate — lead qualification is the highest ROI service for this sector")

    if any(w in area for w in ["law","legal","attorney","solicitor"]) and "support" not in recommended:
        recommended.append("support")
        reasons.append("Law firm — client FAQ bot reduces time spent on routine enquiries dramatically")

    if any(w in area for w in ["clinic","medical","dental","hospital","health"]) and "payments" not in recommended:
        recommended.append("payments")
        reasons.append("Healthcare — automated payment reminders improve collections without awkward calls")

    # Cap at top 3 most relevant
    recommended = list(dict.fromkeys(recommended))[:3]
    reasons     = reasons[:3]

    # Calculate pricing with bundle discount
    setup_total   = sum(SERVICES_PRICING[s]["setup"]   for s in recommended)
    monthly_total = sum(SERVICES_PRICING[s]["monthly"] for s in recommended)
    if len(recommended) >= 3:
        setup_total = int(setup_total * 0.75)
    elif len(recommended) == 2:
        setup_total = int(setup_total * 0.85)

    # Build service rows for email
    svc_rows = ""
    for i, svc in enumerate(recommended):
        p      = SERVICES_PRICING[svc]
        reason = reasons[i] if i < len(reasons) else ""
        svc_rows += f"""
        <tr>
          <td style="padding:11px 16px;border-bottom:1px solid #f0f0f0;vertical-align:top">
            <div style="font-size:13px;font-weight:600;color:#0f1e35">{p['name']}</div>
            <div style="font-size:11px;color:#6b7280;margin-top:3px">{reason}</div>
          </td>
          <td style="padding:11px 16px;border-bottom:1px solid #f0f0f0;text-align:right;white-space:nowrap;vertical-align:top">
            <span style="font-size:13px;font-weight:600;color:#0f1e35">SAR {p['setup']:,}</span>
            <span style="font-size:11px;color:#6b7280"> setup</span><br>
            <span style="font-size:12px;color:#b8922a">SAR {p['monthly']:,}/mo</span>
          </td>
        </tr>"""

    discount_note = ""
    if len(recommended) >= 3:
        discount_note = '<tr><td colspan="2" style="padding:8px 16px;background:#f0f9f4;font-size:11px;color:#16a34a">★ 3-service bundle — 25% setup discount applied</td></tr>'
    elif len(recommended) == 2:
        discount_note = '<tr><td colspan="2" style="padding:8px 16px;background:#f0f9f4;font-size:11px;color:#16a34a">★ 2-service bundle — 15% setup discount applied</td></tr>'

    next_steps = [
        f"Contact {name} on {contact} within 24 hours",
        f"Send tailored proposal for {org} (use universal_proposal.html)",
        "Book a 20-minute demo call — show the live chatbot",
        "Collect 50% upfront before any work begins",
    ]
    steps_html = "".join(
        f'<li style="margin-bottom:8px;font-size:13px;color:#374151">{s}</li>'
        for s in next_steps
    )

    return {
        "recommended":  recommended,
        "setup_total":  setup_total,
        "monthly_total":monthly_total,
        "svc_rows":     svc_rows,
        "discount_note":discount_note,
        "steps_html":   steps_html,
        "city":         city,
        "staff":        staff,
        "revenue":      revenue,
    }


# ── EMAIL BUILDER ─────────────────────────────────────────────────────────────
def build_ia_email(intake, transcript, ref, date_str):
    """Build branded lead email for IA AI Solutions with action plan."""
    name    = intake.get("name","—")
    org     = intake.get("org","—")
    contact = intake.get("contact","—")
    city    = intake.get("city","—")
    area    = intake.get("area","—")
    summ    = intake.get("sum","—") or intake.get("challenge","—")
    staff   = intake.get("staff","—")
    revenue = intake.get("revenue","—")
    current = intake.get("current_intake","—")
    website = intake.get("has_website","—")

    plan = generate_action_plan(intake)

    rows = ""
    for line in transcript.split("\n"):
        if line.startswith("A:") or line.startswith("Assistant:"):
            text = line.split(":",1)[1].strip()
            rows += f'<tr><td style="padding:4px 8px;color:#9ca3af;font-size:12px;width:80px">Assistant</td><td style="padding:4px 8px;font-size:12px;color:#374151">{text}</td></tr>'
        elif line.startswith("C:") or line.startswith("Client:"):
            text = line.split(":",1)[1].strip()
            rows += f'<tr style="background:#f9fafb"><td style="padding:4px 8px;color:#b8922a;font-size:12px;width:80px;font-weight:600">Prospect</td><td style="padding:4px 8px;font-size:12px;color:#111827">{text}</td></tr>'

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 0"><tr><td align="center">
<table width="640" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,.08)">

<tr><td style="background:#080808;padding:24px 32px">
  <table width="100%"><tr>
    <td>
      <div style="margin-bottom:6px">
        <span style="background:#b8922a;color:#080808;font-family:Georgia,serif;font-size:14px;font-weight:600;padding:4px 8px">IA</span>
        <span style="font-family:Georgia,serif;font-size:18px;font-weight:600;color:#fff;margin-left:8px"><span style="color:#b8922a">IA</span> AI Solutions</span>
      </div>
      <p style="margin:0;font-size:12px;color:rgba(255,255,255,.4)">New website lead · {date_str}</p>
    </td>
    <td align="right" style="vertical-align:top">
      <span style="background:#b8922a;color:#080808;font-size:11px;padding:6px 16px;font-weight:600;letter-spacing:.06em">NEW LEAD</span>
    </td>
  </tr></table>
</td></tr>

<tr><td style="padding:24px 32px 0">
  <p style="margin:0 0 12px;font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;border-bottom:1px solid #e5e7eb;padding-bottom:8px">Lead profile</p>
  <table width="100%">
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280;width:140px">Name</td><td style="font-size:13px;color:#111827;font-weight:500">{name}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Business</td><td style="font-size:13px;color:#111827;font-weight:500">{org}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Industry</td><td style="font-size:13px;color:#111827">{area}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">City</td><td style="font-size:13px;color:#111827">{city}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Staff</td><td style="font-size:13px;color:#111827">{staff}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Revenue range</td><td style="font-size:13px;color:#111827">{revenue}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Contact</td><td style="font-size:13px;color:#b8922a;font-weight:600">{contact}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Has website</td><td style="font-size:13px;color:#111827">{website}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Current intake</td><td style="font-size:13px;color:#111827">{current}</td></tr>
  </table>
</td></tr>

<tr><td style="padding:20px 32px 0">
  <p style="margin:0 0 8px;font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;border-bottom:1px solid #e5e7eb;padding-bottom:8px">Main challenge / pain point</p>
  <p style="margin:0;font-size:14px;color:#111827;line-height:1.7;background:#fffbf0;border-left:3px solid #b8922a;padding:12px 16px">{summ}</p>
</td></tr>

<tr><td style="padding:24px 32px 0">
  <p style="margin:0 0 12px;font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;border-bottom:1px solid #e5e7eb;padding-bottom:8px">★ Recommended action plan</p>
  <div style="background:#080808;padding:14px 18px;margin-bottom:14px">
    <p style="margin:0;font-size:13px;color:rgba(255,255,255,.7);line-height:1.6">Based on what <strong style="color:#fff">{name}</strong> said, here is what to propose:</p>
  </div>
  <table width="100%" style="border:1px solid #e5e7eb;border-radius:6px;overflow:hidden">
    <thead><tr style="background:#080808">
      <th style="padding:10px 16px;font-size:10px;color:#b8922a;text-align:left;text-transform:uppercase;letter-spacing:.08em;font-weight:500">Service</th>
      <th style="padding:10px 16px;font-size:10px;color:#b8922a;text-align:right;text-transform:uppercase;letter-spacing:.08em;font-weight:500">Pricing (SAR)</th>
    </tr></thead>
    <tbody>{plan['svc_rows']}</tbody>
    {plan['discount_note']}
    <tfoot><tr style="background:#080808">
      <td style="padding:12px 16px;font-size:13px;font-weight:600;color:#fff">Total</td>
      <td style="padding:12px 16px;text-align:right">
        <span style="font-size:16px;font-weight:600;color:#b8922a">SAR {plan['setup_total']:,}</span>
        <span style="font-size:11px;color:rgba(255,255,255,.4)"> setup</span><br>
        <span style="font-size:13px;color:#b8922a">SAR {plan['monthly_total']:,}/mo</span>
      </td>
    </tr></tfoot>
  </table>
</td></tr>

<tr><td style="padding:20px 32px 0">
  <p style="margin:0 0 12px;font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;border-bottom:1px solid #e5e7eb;padding-bottom:8px">Your next steps</p>
  <ol style="margin:0;padding-left:18px">{plan['steps_html']}</ol>
</td></tr>

<tr><td style="padding:20px 32px">
  <p style="margin:0 0 10px;font-size:10px;color:#9ca3af;text-transform:uppercase;letter-spacing:.1em;border-bottom:1px solid #e5e7eb;padding-bottom:8px">Full conversation</p>
  <table width="100%" style="border:1px solid #e5e7eb;overflow:hidden">{rows}</table>
</td></tr>

<tr><td style="background:#080808;padding:14px 32px">
  <p style="margin:0;font-size:11px;color:rgba(255,255,255,.3)">IA AI Solutions · ia-aisolutions.com · Ref: {ref} · Auto-generated lead notification</p>
</td></tr>

</table></td></tr></table></body></html>"""


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    """AI conversation — used by the website chatbot."""
    try:
        data     = request.json or {}
        messages = data.get("messages", [])
        system   = data.get("system_override", "You are a helpful business assistant for IA AI Solutions.")

        if not messages:
            return jsonify({"error": "messages required"}), 400

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=system,
            messages=messages
        )
        reply = response.content[0].text
        return jsonify({"reply": reply})

    except anthropic.APIError as e:
        print(f"[IA CHAT ERROR] {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/ia-intake", methods=["POST"])
def ia_intake():
    """Receive lead from website chatbot or contact form — send action plan email."""
    try:
        data       = request.json
        intake     = data.get("intake", {})
        transcript = data.get("transcript", "")
        ref        = f"IA-{datetime.now().year}-{random.randint(100,999)}"
        date_str   = datetime.now().strftime("%d %B %Y, %H:%M GST")

        password_clean = EMAIL_PASSWORD.replace(" ", "") if EMAIL_PASSWORD else ""

        org  = intake.get("org","New lead")
        name = intake.get("name","?")
        print(f"[IA INTAKE] New lead: {org} — {name}")

        if EMAIL_SENDER and password_clean and EMAIL_RECIPIENT:
            subject = f"[NEW LEAD] {org} — IA AI Solutions Website — Ref {ref}"
            msg = MIMEMultipart("alternative")
            msg["Subject"]    = subject
            msg["From"]       = f"IA AI Solutions Intake <{EMAIL_SENDER}>"
            msg["To"]         = EMAIL_RECIPIENT
            msg["X-Priority"] = "1"
            msg.attach(MIMEText(build_ia_email(intake, transcript, ref, date_str), "html"))

            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
                    srv.login(EMAIL_SENDER, password_clean)
                    srv.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
                print(f"[IA INTAKE] Lead email sent. Ref: {ref}")
                return jsonify({"sent": True, "ref": ref})
            except smtplib.SMTPAuthenticationError as e:
                print(f"[IA INTAKE] Auth error: {e}")
                return jsonify({"sent": False, "error": "Email auth failed — check App Password on Render"}), 500
            except Exception as e:
                print(f"[IA INTAKE] Email error: {e}")
                return jsonify({"sent": False, "error": str(e)}), 500
        else:
            print("[IA INTAKE] Email not configured")
            return jsonify({"sent": False, "reason": "Email not configured"})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":               "ok",
        "service":              "IA AI Solutions Intake Server",
        "model":                "claude-sonnet-4-6",
        "email_configured":     bool(EMAIL_SENDER and EMAIL_PASSWORD),
        "recipient_configured": bool(EMAIL_RECIPIENT),
        "recipient":            EMAIL_RECIPIENT,
        "timestamp":            datetime.now().isoformat()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

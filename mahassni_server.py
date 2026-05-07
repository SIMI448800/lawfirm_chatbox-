"""
Hassan Mahassni Law Firm — AI Intake Server
File: mahassni_server.py

Dedicated server for The International Law Firm of Hassan Mahassni.
Handles the client intake chatbot, email notifications, and legal memo generation.

Environment variables (set on Render):
  ANTHROPIC_API_KEY    — from console.anthropic.com
  EMAIL_SENDER         — mahassni.intake@gmail.com
  EMAIL_PASSWORD       — Gmail App Password (16 chars)
  EMAIL_RECIPIENT      — firm's email e.g. intake@mahassni.com.sa
  CALENDLY_URL         — https://calendly.com/mahassni/consultation

Render start command:
  gunicorn mahassni_server:app

Routes:
  POST /chat               — AI intake conversation
  POST /send-intake-email  — Send client intake email to firm
  POST /generate-doc       — Generate legal intake memorandum
  GET  /health             — Server health check
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
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "")
CALENDLY_URL    = os.environ.get("CALENDLY_URL", "https://calendly.com/mahassni/consultation")

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are the client intake assistant for The International Law Firm of Hassan Mahassni — one of the oldest and most distinguished law firms in the Kingdom of Saudi Arabia, established in 1970, ranked by Chambers & Partners and Legal 500, associated with Dechert LLP internationally.

Your ONLY job is to collect the client's information professionally and completely. You do NOT assess, filter, or decide whether the firm will take on a matter — that is exclusively the attorney's decision. Accept every enquiry warmly and collect the details. Every person who contacts the firm deserves a professional, welcoming response regardless of the nature of their matter.

Conduct professional intake (2-4 sentences per reply). Extract: full name, organisation, contact (phone/email), jurisdiction, practice area, matter summary, urgency, key dates, parties involved.

Practice areas for routing guidance only (not for filtering): Banking & Finance / Islamic Finance / Project Finance / Corporate & M&A / Joint Ventures / Dispute Resolution & Arbitration / Projects & Energy / Infrastructure / Capital Markets / Real Estate & Construction / Employment / IP & Technology / Regulatory & Compliance / Wills & Succession. If the matter does not clearly fit a category, use "General — Attorney Review Required".

After EVERY reply append this exact block:
|||INTAKE|||{"name":"...","org":"...","contact":"...","juris":"...","lang":"...","area":"...","sum":"...","urg":"normal|high|unknown","dates":"...","parties":"...","complete":false}|||END|||

Set complete:true ONLY when you have: name AND contact AND area AND summary. At that point end your message with: "Thank you — I have everything I need. One of our attorneys will review your matter and be in touch shortly. Would you like to book a consultation now?"

CRITICAL RULES:
- NEVER tell a client their matter is outside the firm's scope or practice areas
- NEVER decline, redirect, or discourage any enquiry for any reason
- NEVER suggest the client contact another firm or seek help elsewhere
- NEVER give legal advice or any opinion on the merits of the matter
- ALWAYS collect the information and let the attorneys decide what to do with it
- Reply in client language (Arabic/English/French) — auto-detect and match
- Professional, warm tone at all times
- Set urg:high for active litigation, regulatory deadlines, or imminent transactions"""

# ── TEAM ROUTING ──────────────────────────────────────────────────────────────
TEAM_MAP = {
    "banking":"Banking & Finance Team","finance":"Banking & Finance Team",
    "islamic":"Banking & Finance Team","project finance":"Projects & Energy Team",
    "corporate":"Corporate & Commercial Team","m&a":"Corporate & Commercial Team",
    "merger":"Corporate & Commercial Team","dispute":"Dispute Resolution Team",
    "arbitration":"Dispute Resolution Team","litigation":"Dispute Resolution Team",
    "energy":"Projects & Energy Team","infrastructure":"Projects & Energy Team",
    "capital":"Capital Markets Team","real estate":"Real Estate & Construction Team",
    "construction":"Real Estate & Construction Team","employment":"Employment Team",
    "ip":"IP & Technology Team","technology":"IP & Technology Team",
    "regulatory":"Regulatory & Compliance Team","wills":"Personal Client Services",
}

def route_team(area):
    a = area.lower()
    for k, v in TEAM_MAP.items():
        if k in a:
            return v
    return "General Intake — Practice Group TBD"

# ── EMAIL BUILDER ─────────────────────────────────────────────────────────────
def build_email(intake, transcript, ref, date_str):
    name    = intake.get("name","—")
    org     = intake.get("org","—")
    contact = intake.get("contact","—")
    juris   = intake.get("juris","—")
    area    = intake.get("area","—")
    summ    = intake.get("sum","—")
    urg     = intake.get("urg","unknown")
    dates   = intake.get("dates","—")
    parties = intake.get("parties","—")
    team    = route_team(area)

    urg_color = "#dc2626" if urg=="high" else "#16a34a" if urg=="normal" else "#6b7280"
    urg_label = "HIGH — PRIORITY FOLLOW-UP" if urg=="high" else "Normal" if urg=="normal" else "Not assessed"
    banner = '<tr><td style="background:#fef2f2;padding:12px 32px;border-left:4px solid #dc2626"><p style="margin:0;font-size:13px;color:#dc2626;font-weight:600">URGENT — Same-day attorney contact recommended.</p></td></tr>' if urg=="high" else ""

    rows = ""
    for line in transcript.split("\n"):
        if line.startswith("Assistant:"):
            rows += f'<tr><td style="padding:4px 8px;color:#9ca3af;font-size:12px;width:80px">Assistant</td><td style="padding:4px 8px;font-size:12px;color:#374151">{line[10:].strip()}</td></tr>'
        elif line.startswith("Client:"):
            rows += f'<tr style="background:#f9fafb"><td style="padding:4px 8px;color:#0f1e35;font-size:12px;width:80px;font-weight:500">Client</td><td style="padding:4px 8px;font-size:12px;color:#111827">{line[7:].strip()}</td></tr>'

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f3f4f6;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 0"><tr><td align="center">
<table width="620" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden">
<tr><td style="background:#0f1e35;padding:24px 32px">
  <table width="100%"><tr>
    <td><p style="margin:0;font-size:18px;font-weight:600;color:#fff;font-family:Georgia,serif">New Client Intake — Hassan Mahassni</p>
        <p style="margin:6px 0 0;font-size:12px;color:#c9a84c">Ref: {ref} &nbsp;·&nbsp; {date_str}</p></td>
    <td align="right"><span style="background:{'#dc2626' if urg=='high' else '#16a34a' if urg=='normal' else '#6b7280'};color:#fff;font-size:11px;padding:5px 14px;border-radius:20px;font-weight:600">{'URGENT' if urg=='high' else 'NORMAL'}</span></td>
  </tr></table>
</td></tr>
{banner}
<tr><td style="padding:20px 32px 0">
  <p style="margin:0 0 4px;font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.07em">Routed to</p>
  <p style="margin:0;font-size:15px;font-weight:600;color:#0f1e35">{team}</p>
</td></tr>
<tr><td style="padding:20px 32px 0">
  <p style="margin:0 0 10px;font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e5e7eb;padding-bottom:8px">Client profile</p>
  <table width="100%">
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280;width:130px">Full name</td><td style="padding:5px 0;font-size:13px;color:#111827;font-weight:500">{name}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Organisation</td><td style="padding:5px 0;font-size:13px;color:#111827">{org}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Contact</td><td style="padding:5px 0;font-size:13px;color:#111827">{contact}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280">Jurisdiction</td><td style="padding:5px 0;font-size:13px;color:#111827">{juris}</td></tr>
  </table>
</td></tr>
<tr><td style="padding:20px 32px">
  <p style="margin:0 0 10px;font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e5e7eb;padding-bottom:8px">Legal matter</p>
  <table width="100%">
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280;width:130px;vertical-align:top">Practice area</td><td style="padding:5px 0;font-size:13px;color:#111827;font-weight:500">{area}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280;vertical-align:top">Summary</td><td style="padding:5px 0;font-size:13px;color:#111827">{summ}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280;vertical-align:top">Urgency</td><td style="padding:5px 0"><span style="color:{urg_color};font-size:12px;font-weight:600">{urg_label}</span></td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280;vertical-align:top">Key dates</td><td style="padding:5px 0;font-size:13px;color:#111827">{dates}</td></tr>
    <tr><td style="padding:5px 0;font-size:13px;color:#6b7280;vertical-align:top">Parties</td><td style="padding:5px 0;font-size:13px;color:#111827">{parties}</td></tr>
  </table>
</td></tr>
<tr><td style="padding:0 32px 20px">
  <p style="margin:0 0 10px;font-size:11px;color:#9ca3af;text-transform:uppercase;letter-spacing:.07em;border-bottom:1px solid #e5e7eb;padding-bottom:8px">Conversation transcript</p>
  <table width="100%" style="border:1px solid #e5e7eb;border-radius:6px;overflow:hidden">{rows}</table>
</td></tr>
<tr><td style="background:#0f1e35;padding:16px 32px">
  <p style="margin:0;font-size:11px;color:rgba(255,255,255,0.35)">Auto-generated by Hassan Mahassni AI Intake System · Ref: {ref} · No legal advice was provided.</p>
</td></tr>
</table></td></tr></table></body></html>"""


# ── ROUTES ────────────────────────────────────────────────────────────────────

@app.route("/chat", methods=["POST"])
def chat():
    """Main AI conversation endpoint."""
    try:
        data     = request.json or {}
        messages = data.get("messages", [])
        system   = data.get("system_override") or SYSTEM_PROMPT

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
        print(f"[CHAT ERROR] {e}")
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/send-intake-email", methods=["POST"])
def send_intake_email():
    """Send intake notification email to Mahassni attorneys."""
    try:
        data       = request.json
        intake     = data.get("intake", {})
        transcript = data.get("transcript", "")
        ref        = f"HM-{datetime.now().year}-{random.randint(100,999)}"
        date_str   = datetime.now().strftime("%d %B %Y, %H:%M GST")

        password_clean = EMAIL_PASSWORD.replace(" ", "") if EMAIL_PASSWORD else ""

        print(f"[MAHASSNI] Intake email triggered — {intake.get('name','?')} | {intake.get('area','?')}")

        if EMAIL_SENDER and password_clean and EMAIL_RECIPIENT:
            urg     = intake.get("urg","normal")
            subject = f"{'🔴 URGENT — ' if urg=='high' else ''}New Client Intake: {intake.get('name','Unknown')} — {intake.get('area','—')} | Ref {ref}"
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"Mahassni Intake System <{EMAIL_SENDER}>"
            msg["To"]      = EMAIL_RECIPIENT
            if urg == "high":
                msg["X-Priority"] = "1"
            msg.attach(MIMEText(build_email(intake, transcript, ref, date_str), "html"))

            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
                    srv.login(EMAIL_SENDER, password_clean)
                    srv.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
                print(f"[MAHASSNI] Email sent. Ref: {ref}")
                return jsonify({"sent": True, "ref": ref})
            except smtplib.SMTPAuthenticationError as e:
                print(f"[MAHASSNI] Auth error: {e}")
                return jsonify({"sent": False, "error": "Email auth failed — check Gmail App Password on Render"}), 500
            except Exception as e:
                print(f"[MAHASSNI] Email error: {e}")
                return jsonify({"sent": False, "error": str(e)}), 500
        else:
            print("[MAHASSNI] Email not configured — skipping send")
            return jsonify({"sent": False, "reason": "Email not configured"})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/generate-doc", methods=["POST"])
def generate_doc():
    """Generate a formatted legal intake memorandum."""
    try:
        data   = request.json or {}
        intake = data.get("intake", {})
        ref    = data.get("ref", f"HM-{datetime.now().year}-{random.randint(100,999)}")

        name    = intake.get("name","—")
        org     = intake.get("org","—")
        contact = intake.get("contact","—")
        juris   = intake.get("juris","—")
        area    = intake.get("area","—")
        summ    = intake.get("sum","—")
        urg     = intake.get("urg","unknown")
        dates   = intake.get("dates","—")
        parties = intake.get("parties","—")
        team    = route_team(area)
        date_str= datetime.now().strftime("%d %B %Y")

        prompt = f"""Draft a professional legal intake memorandum for The International Law Firm of Hassan Mahassni based on this intake data:

Client: {name} / {org}
Contact: {contact}
Jurisdiction: {juris}
Practice Area: {area}
Matter Summary: {summ}
Urgency: {urg}
Key Dates: {dates}
Parties: {parties}
Routed to: {team}
Ref: {ref}
Date: {date_str}

Format as a proper internal legal memorandum with: TO, FROM, DATE, RE, CLIENT INFORMATION, MATTER SUMMARY, RECOMMENDED ACTIONS, and NEXT STEPS sections. Professional tone. Use proper legal language. Keep it concise — one page maximum."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}]
        )

        memo = response.content[0].text
        return jsonify({"memo": memo, "ref": ref, "team": team})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "Mahassni AI Intake Server",
        "model": "claude-sonnet-4-6",
        "email_configured": bool(EMAIL_SENDER and EMAIL_PASSWORD),
        "recipient_configured": bool(EMAIL_RECIPIENT),
        "timestamp": datetime.now().isoformat()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)

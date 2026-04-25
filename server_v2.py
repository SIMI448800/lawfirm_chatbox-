from flask import Flask, request, jsonify
from flask_cors import CORS
import anthropic
import os, smtplib, random
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

app = Flask(__name__)
CORS(app)

# ── SET THESE AS ENVIRONMENT VARIABLES ON RENDER.COM ────────────────────
# ANTHROPIC_API_KEY   your Anthropic key
# EMAIL_SENDER        Gmail you send FROM  e.g. mahassni.intake@gmail.com
# EMAIL_PASSWORD      Gmail App Password (16 chars — NOT your Gmail login)
# EMAIL_RECIPIENT     Firm receives alerts  e.g. intake@mahassni.com.sa
# CALENDLY_URL        e.g. https://calendly.com/mahassni/consultation
# ────────────────────────────────────────────────────────────────────────

client          = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
EMAIL_SENDER    = os.environ.get("EMAIL_SENDER", "")
EMAIL_PASSWORD  = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "")
CALENDLY_URL    = os.environ.get("CALENDLY_URL", "https://calendly.com/mahassni/consultation")

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
  <p style="margin:0;font-size:11px;color:rgba(255,255,255,0.35)">Auto-generated by Hassan Mahassni AI Intake System. No legal advice was provided. Information is unverified and provided by the prospective client.</p>
</td></tr>
</table></td></tr></table></body></html>"""


@app.route("/chat", methods=["POST"])
def chat():
    try:
        data     = request.json
        messages = data.get("messages", [])
        # Allow universal demo to override system prompt per business type
        system   = data.get("system_override", SYSTEM_PROMPT)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=system,
            messages=messages
        )
        return jsonify({"reply": response.content[0].text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/send-intake-email", methods=["POST"])
def send_intake_email():
    try:
        data       = request.json
        intake     = data.get("intake", {})
        transcript = data.get("transcript", "")
        name       = intake.get("name", "Prospective Client")
        area       = intake.get("area", "—")
        urg        = intake.get("urg", "unknown")
        ref        = f"HM-{datetime.now().year}-{random.randint(100,999)}"
        date_str   = datetime.now().strftime("%d %B %Y, %H:%M GST")
        team       = route_team(area)
        subject    = f"{'[URGENT] ' if urg=='high' else ''}New Intake — {name} · {area} · {ref}"

        # Strip spaces from password in case it was copied with spaces from Google
        password_clean = EMAIL_PASSWORD.replace(" ", "") if EMAIL_PASSWORD else ""

        print(f"[EMAIL] Attempting to send to: {EMAIL_RECIPIENT}")
        print(f"[EMAIL] From: {EMAIL_SENDER}")
        print(f"[EMAIL] Password length: {len(password_clean)} chars")

        if EMAIL_SENDER and password_clean and EMAIL_RECIPIENT:
            msg            = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"Mahassni Intake <{EMAIL_SENDER}>"
            msg["To"]      = EMAIL_RECIPIENT
            if urg == "high":
                msg["X-Priority"] = "1"
            msg.attach(MIMEText(build_email(intake, transcript, ref, date_str), "html"))
            try:
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
                    srv.login(EMAIL_SENDER, password_clean)
                    srv.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
                print(f"[EMAIL] Sent successfully. Ref: {ref}")
                return jsonify({"sent": True, "ref": ref, "team": team})
            except smtplib.SMTPAuthenticationError as e:
                print(f"[EMAIL ERROR] Authentication failed: {e}")
                return jsonify({"sent": False, "error": f"Gmail authentication failed: {str(e)}", "ref": ref}), 500
            except smtplib.SMTPException as e:
                print(f"[EMAIL ERROR] SMTP error: {e}")
                return jsonify({"sent": False, "error": f"SMTP error: {str(e)}", "ref": ref}), 500
        else:
            missing = []
            if not EMAIL_SENDER: missing.append("EMAIL_SENDER")
            if not password_clean: missing.append("EMAIL_PASSWORD")
            if not EMAIL_RECIPIENT: missing.append("EMAIL_RECIPIENT")
            print(f"[EMAIL] Missing config: {missing}")
            return jsonify({"sent": False, "ref": ref, "team": team,
                            "reason": f"Missing environment variables: {missing}"})
    except Exception as e:
        print(f"[EMAIL ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/generate-doc", methods=["POST"])
def generate_doc():
    try:
        data        = request.json
        transcript  = data.get("transcript", "")
        intake      = data.get("intake", {})
        biz_name    = data.get("business_name", "The International Law Firm of Hassan Mahassni")
        memo_type   = data.get("memo_type", "Legal Intake Memorandum")
        ref         = f"REF-{datetime.now().year}-{random.randint(100,999)}"
        date_str    = datetime.now().strftime("%d %B %Y")
        response    = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1200,
            messages=[{"role":"user","content":f"""Generate a formal {memo_type} for {biz_name}.
Include: 1. REFERENCE: {ref}  2. DATE: {date_str}  3. CLIENT PROFILE  4. MATTER SUMMARY (3-5 sentences)
5. CATEGORY & RECOMMENDED TEAM  6. URGENCY ASSESSMENT  7. KEY FACTS  8. PARTIES/NOTES
9. RELEVANT DEADLINES  10. RECOMMENDED NEXT STEPS  11. CLIENT PROFILE NOTES
Write in English. Professional format. Clear headers.
TRANSCRIPT:\n{transcript}\nEXTRACTED DATA:\n{str(intake)}"""}]
        )
        return jsonify({"document": response.content[0].text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500




@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status":"ok","email_configured": bool(EMAIL_SENDER and EMAIL_PASSWORD)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

import streamlit as st
from groq import Groq
import json

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Meeting → Action Pipeline",
    page_icon="📋",
    layout="centered",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 2rem; }
    .section-header {
        font-size: 15px; font-weight: 600; margin: 1.2rem 0 0.5rem;
        padding-bottom: 4px; border-bottom: 1px solid #e5e7eb;
    }
    .item-card {
        background: #f9fafb; border: 1px solid #e5e7eb;
        border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;
    }
    .item-text { font-size: 14px; margin-bottom: 6px; }
    .badge {
        display: inline-block; font-size: 11px; font-weight: 600;
        padding: 2px 8px; border-radius: 20px; margin-right: 4px;
    }
    .badge-owner   { background: #dbeafe; color: #1e40af; }
    .badge-due     { background: #fef3c7; color: #92400e; }
    .badge-high    { background: #fee2e2; color: #991b1b; }
    .badge-medium  { background: #fef3c7; color: #92400e; }
    .badge-low     { background: #dcfce7; color: #166534; }
    .badge-noowner { background: #fee2e2; color: #991b1b; }
    .badge-blocker { background: #fee2e2; color: #991b1b; }
    .escalation-box {
        background: #fffbeb; border: 1px solid #f59e0b;
        border-radius: 8px; padding: 12px 16px; margin-top: 1rem;
    }
    .confidence-low {
        background: #fff7ed; border: 1px solid #fb923c;
        border-radius: 6px; padding: 8px 12px; font-size: 13px;
        color: #9a3412; margin-bottom: 1rem;
    }
    .summary-box {
        background: #f0f9ff; border: 1px solid #bae6fd;
        border-radius: 8px; padding: 12px 16px;
        font-size: 14px; color: #0c4a6e; margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Load API key from Streamlit Secrets ───────────────────────────────────────
try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    st.error("⚠️ API key not configured. Please add GROQ_API_KEY to Streamlit Secrets.")
    st.stop()

# ── Sample transcript ─────────────────────────────────────────────────────────
SAMPLE = """[Recording starts mid-conversation]

Sarah: — okay so the Q3 deadline, are we still on track? Because I'm hearing different things.

Mark: Honestly? No. The API integration has been blocked for like two weeks. We need someone to own that.

Dev: I can take it but I need the auth credentials from ops before end of this week or it slips again.

Sarah: Okay so Dev owns API integration, needs creds from ops by Friday. Mark can you follow up with ops today?

Mark: Yeah I'll ping them right after this.

Sarah: Good. What about the dashboard redesign?

Priya: We finished the mockups last Tuesday. Waiting on design sign-off from Lisa but she's been OOO.

Sarah: When does Lisa come back?

Priya: Thursday I think?

Sarah: Okay so Priya follows up with Lisa Thursday. If not responded by EOD Thursday, escalate to me.
If no sign-off by next Monday we decide whether to cut the feature.

Dev: There's also the mobile bug — app crashes on Android 12. Three enterprise customers reported it. High priority.

Sarah: Definitely high priority. Dev, can you fix it by Wednesday?

Dev: Should be doable. I'll need the crash logs from support though.

Sarah: Priya can you get Dev those crash logs by 2pm today?

Priya: Sure.

Sarah: One more thing — hiring a senior backend dev. What happened?

Mark: HR said budget freeze. Unresolved, we need a leadership decision before we can move forward.

Sarah: I'll raise it in the exec meeting Friday."""

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📋 Meeting → Action Pipeline")
st.markdown("Paste a messy meeting transcript — get decisions, action items, owners, and blockers.")
st.divider()

# ── Sidebar info only (no API key input) ──────────────────────────────────────
with st.sidebar:
    st.header("ℹ️ How it works")
    st.markdown("""
1. Paste your meeting transcript
2. Click **Process transcript**
3. Get decisions, action items, owners, deadlines
4. Download Slack or email summary
    """)
    st.markdown("---")
    st.markdown("**What it detects**")
    st.markdown("""
- ✅ Action items with owners
- 🎯 Decisions made
- ❓ Unresolved questions
- ⚠️ Escalations needed
    """)
    st.markdown("---")
    st.caption("Powered by Groq + LLaMA 3.3 70B")

# ── Transcript input ──────────────────────────────────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("#### Paste your transcript")
with col2:
    if st.button("Load sample", use_container_width=True):
        st.session_state["load_sample"] = True

default_text = SAMPLE if st.session_state.get("load_sample") else ""

transcript = st.text_area(
    label="transcript",
    label_visibility="collapsed",
    value=default_text,
    placeholder="Paste raw meeting transcript here — messy, with crosstalk, incomplete sentences — all fine...",
    height=220,
    key="transcript_input"
)

process_btn = st.button("▶  Process transcript", type="primary", use_container_width=True)

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a meeting intelligence assistant. Extract structured data from meeting transcripts.
Return ONLY valid JSON, no markdown, no explanation, no code blocks. Use this exact schema:

{
  "summary": "2-3 sentence meeting summary",
  "decisions": [
    { "text": "decision made", "owner": "person or null" }
  ],
  "action_items": [
    { "text": "what needs to be done", "owner": "person or null", "due": "deadline or null", "priority": "high|medium|low" }
  ],
  "unresolved": [
    { "text": "question or issue not resolved", "blocker": true }
  ],
  "escalations": [
    "things that need human judgment or leadership decision"
  ],
  "participants": ["names mentioned"],
  "confidence": "high|medium|low",
  "confidence_note": "brief note if medium or low confidence"
}

Rules:
- Extract only what is explicitly stated or clearly implied. Do not invent anything.
- If transcript is too short or noisy, set confidence to low.
- Mark escalations for: unresolved budget decisions, missing owners on critical tasks, anything needing leadership input.
- Keep all text concise, 1 sentence max per item.
- Return raw JSON only. No markdown. No backticks. No explanation."""

# ── Helper renderers ──────────────────────────────────────────────────────────
def badge(text, cls):
    return f'<span class="badge badge-{cls}">{text}</span>'

def render_action_items(items):
    if not items:
        return
    st.markdown('<div class="section-header">✅ Action Items</div>', unsafe_allow_html=True)
    for a in items:
        priority = a.get("priority", "medium")
        owner    = a.get("owner")
        due      = a.get("due")
        badges = ""
        if owner:
            badges += badge(f"👤 {owner}", "owner")
        else:
            badges += badge("⚠ no owner", "noowner")
        if due:
            badges += badge(f"📅 {due}", "due")
        badges += badge(f"{priority} priority", priority)
        st.markdown(f"""
        <div class="item-card">
            <div class="item-text">{a['text']}</div>
            <div>{badges}</div>
        </div>""", unsafe_allow_html=True)

def render_decisions(items):
    if not items:
        return
    st.markdown('<div class="section-header">🎯 Decisions Made</div>', unsafe_allow_html=True)
    for d in items:
        owner_badge = badge(f"👤 {d['owner']}", "owner") if d.get("owner") else ""
        st.markdown(f"""
        <div class="item-card">
            <div class="item-text">{d['text']}</div>
            <div>{owner_badge}</div>
        </div>""", unsafe_allow_html=True)

def render_unresolved(items):
    if not items:
        return
    st.markdown('<div class="section-header">❓ Unresolved Questions</div>', unsafe_allow_html=True)
    for u in items:
        blocker_badge = badge("🚧 blocker", "blocker") if u.get("blocker") else ""
        st.markdown(f"""
        <div class="item-card">
            <div class="item-text">{u['text']}</div>
            <div>{blocker_badge}</div>
        </div>""", unsafe_allow_html=True)

def render_escalations(items):
    if not items:
        return
    st.markdown('<div class="section-header">⚠️ Needs Human Judgment</div>', unsafe_allow_html=True)
    st.markdown('<div class="escalation-box">', unsafe_allow_html=True)
    for e in items:
        st.markdown(f"• {e}")
    st.markdown('</div>', unsafe_allow_html=True)

def build_slack_text(d):
    lines = [f"*📋 Meeting Summary*\n{d.get('summary', '')}"]
    if d.get("action_items"):
        lines.append("\n*✅ Action Items*")
        for a in d["action_items"]:
            line = f"• {a['text']}"
            if a.get("owner"): line += f" → *{a['owner']}*"
            if a.get("due"):   line += f" _({a['due']})_"
            if a.get("priority") == "high": line += " 🔴"
            lines.append(line)
    if d.get("unresolved"):
        lines.append("\n*❓ Unresolved*")
        for u in d["unresolved"]:
            lines.append(f"• {u['text']}" + (" 🚧" if u.get("blocker") else ""))
    if d.get("escalations"):
        lines.append("\n*⚠️ Needs attention*")
        for e in d["escalations"]:
            lines.append(f"• {e}")
    return "\n".join(lines)

def build_email_text(d):
    lines = ["Meeting Summary", "─" * 40, "", d.get("summary", ""), ""]
    if d.get("decisions"):
        lines += ["Decisions Made"]
        for dec in d["decisions"]:
            lines.append(f"  • {dec['text']}" + (f" ({dec['owner']})" if dec.get("owner") else ""))
        lines.append("")
    if d.get("action_items"):
        lines += ["Action Items"]
        for a in d["action_items"]:
            line = f"  • {a['text']}"
            if a.get("owner"): line += f"  —  Owner: {a['owner']}"
            if a.get("due"):   line += f"  —  Due: {a['due']}"
            lines.append(line)
        lines.append("")
    if d.get("unresolved"):
        lines += ["Open Questions"]
        for u in d["unresolved"]:
            lines.append(f"  • {u['text']}")
        lines.append("")
    if d.get("escalations"):
        lines += ["Requires Decision / Follow-up"]
        for e in d["escalations"]:
            lines.append(f"  • {e}")
    return "\n".join(lines)

# ── Main processing ───────────────────────────────────────────────────────────
if process_btn:
    text = transcript.strip()

    if not text:
        st.error("Please paste a meeting transcript first.")
    else:
        with st.spinner("Analyzing transcript..."):
            try:
                client = Groq(api_key=api_key)
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": f"Transcript:\n\n{text}"}
                    ],
                    temperature=0.1,
                    max_tokens=1024,
                )
                raw   = response.choices[0].message.content
                clean = raw.replace("```json", "").replace("```", "").strip()
                data  = json.loads(clean)
                st.session_state["result"] = data

            except json.JSONDecodeError:
                st.error("Could not parse the AI response. Try again or simplify the transcript.")
            except Exception as e:
                err = str(e)
                if "401" in err or "invalid_api_key" in err.lower():
                    st.error("Invalid API key in Streamlit Secrets. Please check GROQ_API_KEY.")
                elif "429" in err:
                    st.error("Rate limit hit. Please wait a moment and try again.")
                else:
                    st.error(f"Something went wrong: {err}")

# ── Render results ────────────────────────────────────────────────────────────
if "result" in st.session_state:
    d = st.session_state["result"]

    st.divider()

    if d.get("participants"):
        st.caption("👥 Participants: " + ", ".join(d["participants"]))

    if d.get("confidence") in ("low", "medium"):
        note = d.get("confidence_note", "")
        st.markdown(
            f'<div class="confidence-low">⚠️ Confidence: <b>{d["confidence"]}</b>'
            + (f" — {note}" if note else "") + "</div>",
            unsafe_allow_html=True
        )

    if d.get("summary"):
        st.markdown(f'<div class="summary-box">{d["summary"]}</div>', unsafe_allow_html=True)

    render_action_items(d.get("action_items", []))
    render_decisions(d.get("decisions", []))
    render_unresolved(d.get("unresolved", []))
    render_escalations(d.get("escalations", []))

    st.divider()
    st.markdown("#### 📤 Export")
    col_slack, col_email = st.columns(2)

    with col_slack:
        st.download_button(
            label="⬇ Download Slack digest",
            data=build_slack_text(d),
            file_name="slack_digest.txt",
            mime="text/plain",
            use_container_width=True
        )
    with col_email:
        st.download_button(
            label="⬇ Download email summary",
            data=build_email_text(d),
            file_name="meeting_summary.txt",
            mime="text/plain",
            use_container_width=True
        )

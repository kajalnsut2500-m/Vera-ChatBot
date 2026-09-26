from __future__ import annotations

import re
from typing import Any

from app.models.common import CTAKind, SendAs
from app.models.tick_io import TickAction

# ── consent mapping ───────────────────────────────────────────────────────────

_CONSENT_REQUIRED: dict[str, str] = {
    "recall_due": "recall_reminders",
    "appointment_reminder": "appointment_reminders",
    "wedding_package_followup": "promotional_offers",
    "bridal_followup": "promotional_offers",
}

# ── helpers ───────────────────────────────────────────────────────────────────

def _uses_hindi(merchant: dict) -> bool:
    return "hi" in merchant.get("identity", {}).get("languages", [])


def _name(merchant: dict) -> str:
    return merchant.get("identity", {}).get("name", "")


def _owner(merchant: dict) -> str:
    return merchant.get("identity", {}).get("owner_first_name", "") or _name(merchant)


def _find_digest(category: dict, item_id: str) -> dict:
    for d in category.get("digest", []):
        if d.get("id") == item_id:
            return d
    return {}


def _check_taboos(body: str, category: dict) -> bool:
    taboos = category.get("voice", {}).get("vocab_taboo", [])
    lower = body.lower()
    return not any(t.lower() in lower for t in taboos)


def _check_consent(trigger: dict, customer: dict | None) -> bool:
    kind = trigger.get("kind", "")
    required = _CONSENT_REQUIRED.get(kind)
    if required is None:
        return True  # no consent required for merchant-facing triggers
    if customer is None:
        return False
    scope = customer.get("consent", {}).get("scope", [])
    return required in scope


def _already_sent(body: str, prior_bodies: list[str]) -> bool:
    return body in prior_bodies


def _conv_id(merchant_id: str, trigger_id: str) -> str:
    return f"conv_{merchant_id}_{trigger_id}"


# ── per-kind builders ─────────────────────────────────────────────────────────

def _build_research_digest(trigger: dict, merchant: dict, category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    item = _find_digest(category, trigger.get("payload", {}).get("top_item_id", ""))
    owner = _owner(merchant)
    title = item.get("title", "a new research finding")
    source = item.get("source", "a research source")
    n = item.get("trial_n", 0)
    segment = item.get("patient_segment", "patients")
    n_str = f"{n:,}" if n else ""

    if hi:
        body = (
            f"{owner}, {source} mein ek nayi finding aayi"
            + (f" — {n_str}-patient study mein: {title}" if n_str else f": {title}")
            + f". Aapke {segment} ke liye relevant ho sakta hai. Reply YES."
        )
    else:
        body = (
            f"{owner}, {source} just landed"
            + (f" — {n_str}-patient study: {title}" if n_str else f": {title}")
            + f". Relevant to your {segment}. Reply YES for the abstract, STOP to skip."
        )
    params = [owner, f"{source}: {title}", "Reply YES / STOP"]
    return body, "vera_research_digest_v1", "binary_yes_stop", params


def _build_regulation_change(trigger: dict, merchant: dict, category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    payload = trigger.get("payload", {})
    item = _find_digest(category, payload.get("top_item_id", ""))
    owner = _owner(merchant)
    title = item.get("title", "a compliance update")
    deadline = payload.get("deadline_iso", "")
    deadline_str = f" Deadline: {deadline}." if deadline else ""

    if hi:
        body = f"{owner}, compliance update: {title}.{deadline_str} Reply YES to check impact on your practice."
    else:
        body = f"{owner}, compliance update: {title}.{deadline_str} Reply YES to see what needs to change."
    params = [owner, title, deadline]
    return body, "vera_regulation_change_v1", "binary_yes_stop", params


def _build_perf_dip(trigger: dict, merchant: dict, _category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    p = trigger.get("payload", {})
    owner = _owner(merchant)
    metric = p.get("metric", "performance")
    delta = p.get("delta_pct", 0)
    delta_abs = abs(int(delta * 100)) if delta else 0
    window = p.get("window", "7d")

    if hi:
        body = f"{owner}, is hafte aapki {metric} {delta_abs}% girar aayi ({window} window mein). Quick fix dekhna chahenge? Reply YES."
    else:
        body = f"{owner}, your {metric} dropped {delta_abs}% this {window}. Want a quick breakdown and fix? Reply YES."
    params = [owner, f"{metric} -{delta_abs}%", window]
    return body, "vera_perf_dip_v1", "binary_yes_stop", params


def _build_perf_spike(trigger: dict, merchant: dict, _category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    p = trigger.get("payload", {})
    owner = _owner(merchant)
    metric = p.get("metric", "views")
    delta = p.get("delta_pct", 0)
    delta_abs = abs(int(delta * 100)) if delta else 0

    body = (
        f"{owner}, aapki {metric} is hafte {delta_abs}% upar aayi! Yeh momentum capture karein — ek offer post karein? Reply YES."
        if hi else
        f"{owner}, your {metric} is up {delta_abs}% this week! Good time to push an offer or post. Want me to draft? Reply YES."
    )
    params = [owner, f"{metric} +{delta_abs}%", "Reply YES"]
    return body, "vera_perf_spike_v1", "binary_yes_no", params


def _build_renewal_due(trigger: dict, merchant: dict, _category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    p = trigger.get("payload", {})
    owner = _owner(merchant)
    days = p.get("days_remaining", merchant.get("subscription", {}).get("days_remaining", "?"))
    plan = p.get("plan", merchant.get("subscription", {}).get("plan", "Pro"))
    amount = p.get("renewal_amount", "")
    price_str = f" (₹{amount})" if amount else ""

    if hi:
        body = f"{owner}, aapka {plan} plan sirf {days} din mein expire ho raha hai. Listing pause ho jayegi. Reply YES to renew{price_str}."
    else:
        body = f"{owner}, your {plan} subscription expires in {days} days — listing pauses after that. Reply YES to renew{price_str}, STOP to skip."
    params = [owner, f"{plan} — {days} days left", f"Renewal{price_str}"]
    return body, "vera_renewal_due_v1", "binary_yes_stop", params


def _build_recall_due(trigger: dict, merchant: dict, _category: dict, customer: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    p = trigger.get("payload", {})
    c_name = customer.get("identity", {}).get("name", "")
    m_name = merchant.get("identity", {}).get("name", "")
    service = p.get("service_due", "cleaning").replace("_", " ")
    slots = p.get("available_slots", [])
    slot_strs = [s.get("label", "") for s in slots[:2] if s.get("label")]
    slot_text = " ya ".join(slot_strs) if hi else " or ".join(slot_strs)
    slot_line = f" {slot_text}." if slot_text else ""

    if hi:
        body = f"Hi {c_name}, {m_name} se bol rahe hain. Aapka {service} recall due hai.{slot_line} Reply 1 ya 2 to book."
    else:
        body = f"Hi {c_name}, {m_name} here. Your {service} recall is due.{slot_line} Reply 1 for first slot, 2 for second."
    params = [c_name, m_name, service, slot_text]
    return body, "merchant_recall_reminder_v1", "multi_choice_slot", params


def _build_festival(trigger: dict, merchant: dict, category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    p = trigger.get("payload", {})
    owner = _owner(merchant)
    festival = p.get("festival", "the upcoming festival")
    days = p.get("days_until", "")
    days_str = f" {days} days away" if days else ""
    active_offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    offer_hint = f" using your existing '{active_offers[0]['title']}'" if active_offers else ""

    if hi:
        body = f"{owner}, {festival}{days_str} aa raha hai. Ek seasonal offer draft kar sakte hain{offer_hint}. Chalega? Reply YES."
    else:
        body = f"{owner}, {festival} is{days_str}. I can draft a seasonal offer{offer_hint}. Worth a quick post? Reply YES."
    params = [owner, festival, days_str.strip()]
    return body, "vera_festival_v1", "binary_yes_no", params


def _build_dormant(trigger: dict, merchant: dict, category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    owner = _owner(merchant)
    perf = merchant.get("performance", {})
    views = perf.get("views", 0)
    calls = perf.get("calls", 0)
    ctr = perf.get("ctr", 0.0)
    peer_ctr = category.get("peer_stats", {}).get("avg_ctr", 0.0)
    ctr_str = f"{ctr:.1%}"
    peer_str = f"{peer_ctr:.1%}"

    if hi:
        body = f"{owner}, 30 din mein {views} views, {calls} calls — CTR {ctr_str} (peer median {peer_str}). Ek change se improve ho sakta hai. Reply YES."
    else:
        body = f"{owner}, last 30 days: {views} views, {calls} calls, CTR {ctr_str} (peer median {peer_str}). One change usually moves this. Reply YES."
    params = [owner, f"{views} views / {calls} calls", f"CTR {ctr_str} vs {peer_str}"]
    return body, "vera_dormant_v1", "binary_yes_no", params


def _build_milestone(trigger: dict, merchant: dict, _category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    p = trigger.get("payload", {})
    owner = _owner(merchant)
    mtype = p.get("milestone_type", "milestone").replace("_", " ")
    val = p.get("value", "")
    desc = f"{val} {mtype}" if val else mtype

    if hi:
        body = f"{owner}, milestone — {desc}! Google post draft karein? Reply YES."
    else:
        body = f"{owner}, milestone — {desc}! Worth sharing on your Google profile. Want a quick post draft? Reply YES."
    params = [owner, desc, "Reply YES"]
    return body, "vera_milestone_v1", "open_ended", params


def _build_curious_ask(trigger: dict, merchant: dict, _category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    p = trigger.get("payload", {})
    owner = _owner(merchant)
    ask_map = {
        "what_service_in_demand_this_week": "which service are customers asking about most this week?",
        "what_peak_hours": "what are your busiest hours on weekdays?",
        "recent_customer_feedback": "what's the most common positive thing customers say about your place?",
    }
    question = ask_map.get(p.get("ask_template", ""), "what's been on your customers' minds recently?")

    if hi:
        body = f"{owner}, ek quick sawaal: {question}"
    else:
        body = f"{owner}, quick question: {question}"
    params = [owner, question, ""]
    return body, "vera_curious_ask_v1", "open_ended", params


def _build_review_theme(trigger: dict, merchant: dict, _category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    p = trigger.get("payload", {})
    owner = _owner(merchant)
    theme = p.get("theme", "a recurring theme")
    sentiment = p.get("sentiment", "")
    count = p.get("occurrences_30d", "")
    count_str = f"{count} mentions" if count else "recent mentions"
    label = "positive" if sentiment == "pos" else "negative" if sentiment == "neg" else sentiment

    if hi:
        body = f"{owner}, reviews mein ek pattern hai — '{theme}' ({label}, {count_str} is month). Strategy banaein? Reply YES."
    else:
        body = f"{owner}, noticed a pattern in reviews — '{theme}' ({label}, {count_str} this month). Want to address it? Reply YES."
    params = [owner, theme, count_str]
    return body, "vera_review_theme_v1", "binary_yes_stop", params


def _build_generic(trigger: dict, merchant: dict, category: dict, hi: bool) -> tuple[str, str, str, list[str]]:
    owner = _owner(merchant)
    kind = trigger.get("kind", "update").replace("_", " ")
    if hi:
        body = f"{owner}, aapke account mein ek {kind} hai. Details dekhna chahenge? Reply YES."
    else:
        body = f"{owner}, there's a {kind} for your account worth reviewing. Reply YES for details, STOP to skip."
    params = [owner, kind, "Reply YES / STOP"]
    return body, f"vera_{trigger.get('kind', 'generic')}_v1", "binary_yes_stop", params


# ── main entry point ──────────────────────────────────────────────────────────

_BUILDERS = {
    "research_digest": _build_research_digest,
    "regulation_change": _build_regulation_change,
    "perf_dip": _build_perf_dip,
    "perf_spike": _build_perf_spike,
    "renewal_due": _build_renewal_due,
    "festival_upcoming": _build_festival,
    "dormant_with_vera": _build_dormant,
    "milestone_reached": _build_milestone,
    "curious_ask_due": _build_curious_ask,
    "review_theme_emerged": _build_review_theme,
}


def compose(
    trigger: dict,
    merchant: dict,
    category: dict,
    customer: dict | None,
    prior_bodies: list[str],
) -> TickAction | None:
    if not _check_consent(trigger, customer):
        return None

    kind = trigger.get("kind", "")
    hi = _uses_hindi(merchant)
    scope = trigger.get("scope", "merchant")

    if scope == "customer" and kind == "recall_due" and customer:
        body, tname, cta_str, params = _build_recall_due(trigger, merchant, category, customer, hi)
        send_as = SendAs.merchant_on_behalf
    else:
        builder = _BUILDERS.get(kind, _build_generic)
        if kind == "recall_due":
            return None  # customer trigger but no customer ctx
        body, tname, cta_str, params = builder(trigger, merchant, category, hi)
        send_as = SendAs.vera

    if not _check_taboos(body, category):
        return None
    if _already_sent(body, prior_bodies):
        return None

    merchant_id = merchant.get("merchant_id", trigger.get("merchant_id", ""))
    trigger_id = trigger.get("id", "")
    conv_id = _conv_id(merchant_id, trigger_id)
    cid = customer.get("customer_id") if customer else None

    return TickAction(
        conversation_id=conv_id,
        merchant_id=merchant_id,
        customer_id=cid,
        send_as=send_as,
        trigger_id=trigger_id,
        template_name=tname,
        template_params=[str(p) for p in params],
        body=body,
        cta=CTAKind(cta_str),
        suppression_key=trigger.get("suppression_key", ""),
        rationale=(
            f"Trigger kind={kind}, urgency={trigger.get('urgency',1)}, "
            f"merchant={merchant_id}, send_as={send_as.value}"
        ),
    )

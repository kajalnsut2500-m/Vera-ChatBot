from __future__ import annotations

from enum import Enum


class Scope(str, Enum):
    category = "category"
    merchant = "merchant"
    customer = "customer"
    trigger = "trigger"


class CTAKind(str, Enum):
    binary_yes_stop = "binary_yes_stop"
    binary_yes_no = "binary_yes_no"
    binary_confirm_cancel = "binary_confirm_cancel"
    open_ended = "open_ended"
    multi_choice_slot = "multi_choice_slot"
    none = "none"


class ActionKind(str, Enum):
    send = "send"
    wait = "wait"
    end = "end"


class SendAs(str, Enum):
    vera = "vera"
    merchant_on_behalf = "merchant_on_behalf"

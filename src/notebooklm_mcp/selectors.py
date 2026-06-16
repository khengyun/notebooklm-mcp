"""
Single source of truth for NotebookLM DOM selectors.

NotebookLM is an Angular-Material app whose markup shifts between releases, so
every selector lives here (not scattered through the client) to make UI-drift
maintenance a one-file change.

Design rules (why these selectors and not others):

* Prefer **class / structural** hooks over visible text. NotebookLM is localized
  (the chat box placeholder is "Ask a question..." in English but
  "Đặt câu hỏi..." in Vietnamese, etc.), so any ``placeholder*='Ask'`` selector
  is locale-dependent and unreliable. ``textarea.query-box-input`` is stable
  across locales — verified live against a real account (2026-06).
* Every group is an ordered fallback list: the most specific/verified selector
  first, looser fallbacks after. The client tries them in order.
* The deliberately-generic ``textarea:not([disabled])`` catch-all is **excluded
  on purpose** — on a real notebook it matches the "find new sources" textarea
  *before* the chat box and silently sends to the wrong field.
"""

from __future__ import annotations

# The chat composer (textarea you type the question into).
# Verified live: <textarea class="... query-box-input ...">.
CHAT_INPUT: list[str] = [
    "textarea.query-box-input",
    'textarea[aria-label="Input for queries"]',
    'textarea[aria-label="Enter a query"]',
    "textarea.query-box-textarea:not(.mat-mdc-autocomplete-trigger)",
]

# Optional explicit "send" button. Sending via Enter is primary; this is a
# fallback for when Enter is intercepted.
SEND_BUTTON: list[str] = [
    'button[aria-label*="Send" i]',
    'button[type="submit"].send-button',
    "button.send-button",
]

# Assistant response bubbles. ``.to-user-container`` wraps messages *to* the
# user (the model's answers); ``.message-text-content`` is the rendered text.
# Verified live: ".to-user-container .message-text-content" isolates AI answers
# from the user's own echoed messages.
RESPONSE: list[str] = [
    ".to-user-container .message-text-content",
    "chat-message .to-user-container .message-text-content",
    ".chat-message-container .to-user-container",
]

# "Model is generating" indicator. Present only while a response streams.
THINKING: list[str] = [
    "div.thinking-message",
    ".thinking-message",
    "[class*='thinking-message']",
]

# URL fragments that mean we were bounced to a Google sign-in flow (not authed).
SIGNED_OUT_URL_MARKERS: tuple[str, ...] = (
    "accounts.google.com",
    "/signin",
    "ServiceLogin",
    "/ServiceLogin",
)

# Host that means we are inside the NotebookLM app (not an interstitial).
APP_HOST: str = "notebooklm.google.com"

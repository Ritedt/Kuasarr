# -*- coding: utf-8 -*-
# Kuasarr

NOTIFICATION_PROVIDERS = ("discord", "telegram")

KUASARR_AVATAR = "https://raw.githubusercontent.com/rix1337/kuasarr/main/kuasarr.png"

# Discord message flag for suppressing notifications
SUPPRESS_NOTIFICATIONS = 1 << 12  # 4096

# Request timeout for notification HTTP calls
SESSION_REQUEST_TIMEOUT_SECONDS = 30

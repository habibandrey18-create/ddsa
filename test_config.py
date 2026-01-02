#!/usr/bin/env python3
"""Test config loading"""

import config

print("YANDEX_REF_CLID:", config.YANDEX_REF_CLID)
print("YANDEX_REF_VID:", config.YANDEX_REF_VID)
print("YANDEX_REF_ERID:", config.YANDEX_REF_ERID)
print("GROQ_API_KEY loaded:", bool(config.GROQ_API_KEY))
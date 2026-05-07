# bash_eicr_templater.py
#
# Simple python helper script to replace the lab code string name in a
# dummy eICR with a narrative free text input representing a nonstandard
# test case. Also adds a fresh UUID to the dummy eICR.

import os
import re
import uuid
from xml.sax.saxutils import escape
from xml.sax.saxutils import quoteattr

with open(os.environ["SOURCE_EICR"]) as fp:
    src = fp.read()
name = os.environ["INPUT"]

src = re.sub(
    r'displayName="[^"]*"',
    "displayName=" + quoteattr(name),
    src,
    count=1,
)
src = re.sub(
    r"(<originalText[^>]*>)[^<]*(</originalText>)",
    lambda m: m.group(1) + escape(name) + m.group(2),
    src,
    count=1,
)
src = re.sub(
    r'<id root="[0-9a-f-]+"',
    f'<id root="{uuid.uuid4()}"',
    src,
    count=1,
)
src = re.sub(
    r'<setId extension="[0-9a-f-]+"',
    f'<setId extension="{uuid.uuid4()}"',
    src,
    count=1,
)

with open(os.environ["OUT_PATH"], "w") as fp:
    fp.write(src)

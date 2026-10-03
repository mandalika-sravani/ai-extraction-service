"""CLI demo: python main.py  (or: python main.py "some text")"""
import json
import importlib
import logging
import sys

try:
    importlib.import_module("dotenv").load_dotenv()  # loads ANTHROPIC_API_KEY from .env
except ModuleNotFoundError:
    pass  # dotenv is optional when environment variables are set externally

from extractor import ExtractionError, Extractor
from schemas import ContactList

SAMPLE = """From: Priya Sharma <priya.sharma@nimbuslabs.io>
To: Arjun Mehta
Subject: Re: Re: Fwd: Vendor intro + next steps

Hi Arjun,

Great meeting yesterday! As promised, looping in a few people.

Rahul from our finance side will handle the PO - you can reach him at
rahul.k@nimbuslabs.io. He's usually quicker on WhatsApp: 98480 55120.

For the technical integration, please talk to Dr. Elena Varga (Principal ML
Engineer). She's based in our London office, +44 20 7946 0958, or email
e.varga[at]nimbuslabs[dot]io.

Also, my old colleague Tom Becker (now CTO at Brightwave Analytics) asked
to be introduced - tom@brightwave.co. Don't call his office line
(555) 014-2290 ext. 204, he never picks up.

Oh, and someone from Acme Corp called about the RFP but didn't leave a name.

Thanks,
Priya

--
Priya Sharma | Head of Data
Nimbus Labs Pvt. Ltd.
M: +91 98480 22334
W: nimbuslabs.io

-----Original Message-----
From: Arjun Mehta <arjun@datavine.in>
Sent: Monday, 28 September 2026 4:12 PM

Hi Priya, thanks for your time today. I'm the founder of DataVine, happy to
connect with your team. My number is 040-2345 6789 if anyone needs it.
Arjun"""

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    text = sys.argv[1] if len(sys.argv) > 1 else SAMPLE
    try:
        result = Extractor(ContactList).extract(text)
        print(json.dumps(result.model_dump(), indent=2))
    except ExtractionError as e:
        print(f"Extraction failed: {e}", file=sys.stderr)
        sys.exit(1)

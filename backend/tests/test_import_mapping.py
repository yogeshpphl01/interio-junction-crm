"""
<test-module name="test_import_mapping">
  <purpose>
    Validate the pure Meta Lead-Ads -> CRM lead mapping in meta_import.py. No DB,
    no FastAPI, no auth — just the column translation that the importer relies on.
  </purpose>
</test-module>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import meta_import as m  # noqa: E402


def test_humanize():
    assert m.humanize("in_the_next_1_month_") == "In the next 1 month"
    assert m.humanize("woodwork:_kitchen,_wardrobe_and_bed") == "Woodwork: kitchen, wardrobe and bed"
    assert m.humanize(None) == ""


def test_map_bedrooms():
    assert m.map_bedrooms("2") == "2 BHK"
    assert m.map_bedrooms("4+") == "4 BHK"
    assert m.map_bedrooms("5") == "5 BHK"
    assert m.map_bedrooms("7") == "Villa"
    assert m.map_bedrooms(None) == "2 BHK"
    assert m.map_bedrooms("") == "2 BHK"


def test_map_source():
    assert m.map_source("ig") == "Instagram"
    assert m.map_source("fb") == "Facebook"
    assert m.map_source("") == "Other"
    assert m.map_source(None) == "Other"


def test_parse_created_time_to_utc():
    # +05:30 IST -> UTC (subtract 5h30m)
    assert m.parse_created_time("2026-05-27T19:30:35+05:30") == "2026-05-27T14:00:35+00:00"
    assert m.parse_created_time("") is None
    assert m.parse_created_time("not-a-date") is None


def test_clean_phone():
    assert m.clean_phone("+9180079 00780") == "+918007900780"
    assert m.clean_phone(None) == ""


def test_pick_avoids_ambiguous_substring():
    # 'id' must NOT match 'ad_id'/'campaign_id'; exact 'id' wins.
    row = {"ad_id": "ag:1", "campaign_id": "c:1", "id": "l:99"}
    assert m.pick(row, "id", "lead_id") == "l:99"


def test_build_requirements():
    txt = m.build_requirements("modular_kitchen", "as_soon_as_possible", "price", "10th Oct Modular factory")
    assert txt == "Scope: Modular kitchen. Timeline: As soon as possible. Priority: Price. (Campaign: 10th Oct Modular factory)"


def test_map_meta_row_full():
    row = {
        "id": "l:123", "created_time": "2026-05-27T19:30:35+05:30", "campaign_name": "Camp",
        "platform": "ig", "number_of_bedrooms": "3", "what's_the_scope_of_work": "modular_kitchen",
        "when_would_you_like_to_start_your_project?": "in_the_next_1_month_",
        "what_is_most_important_to_you?": "design", "email": "a@b.com", "full_name": "  Asha  ",
        "whatsapp_number": "+91 90000 11111", "city": "Pune", "is_organic": "false",
    }
    lead = m.map_meta_row(row, "uploader-1", "batch-1", "2026-06-20T00:00:00+00:00")
    assert lead["full_name"] == "Asha"
    assert lead["email"] == "a@b.com"
    assert lead["phone"] == "+919000011111"
    assert lead["city"] == "Pune"
    assert lead["bhk_type"] == "3 BHK"
    assert lead["source"] == "Instagram"
    assert lead["meta_lead_id"] == "l:123"
    assert lead["stage"] == 1 and lead["status"] == "Active"
    assert lead["lifecycle_phase"] == "Enquiry" and lead["furthest_stage"] == 1
    assert lead["is_organic"] is False
    assert lead["created_at"] == "2026-05-27T14:00:35+00:00"
    assert lead["journey"][0]["stage"] == 1


def test_map_meta_row_blank_contact_marked_unknown():
    lead = m.map_meta_row({"id": "l:1", "platform": "fb"}, "u", "b", "2026-06-20T00:00:00+00:00")
    assert lead["full_name"] == "Unknown"
    assert lead["phone"] == ""
    assert lead["source"] == "Facebook"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  ok  {fn.__name__}")
        except Exception:
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")

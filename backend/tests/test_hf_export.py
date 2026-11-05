from pathlib import Path
from types import SimpleNamespace

import pytest

from app.hf_export import (
    MASK,
    PublicRepoError,
    allocate_parts,
    build_row,
    mask_ids,
    matches_category,
    segment_paragraphs,
    select_judgments,
    upload,
)

FIX = Path(__file__).parent / "fixtures"


def test_mask_ids_removes_national_ids_but_keeps_trade_mark_numbers():
    text, n = mask_ids("You, Tan, male 35 years old NRIC No: S1234567A are charged")
    assert n == 1 and "S1234567A" not in text and MASK in text
    text, n = mask_ids("the Rooster Sign in Singapore as Trade Mark No T9012345B (ie)")
    assert n == 0 and "T9012345B" in text


@pytest.mark.parametrize("raw", [
    "NRIC No S 1234567 A are charged", "Fin No G-1234567-K, male", "(Passport No: AH 30769)",
    "NRIC No. 0123456-B of Blk 5", "estate of Tan (nric no. s1234567a)",
    "NRIC NO: S1234567/Z, Hereby", "Tan (NRIC) 1234567/G shall return", "NRIC No1234567/D, are charged", "Tan i/c SC 1234567-J hereinafter",
    "a passport bearing serial number WW1234567 and", "passport with the number A1234567.",
])
def test_mask_ids_catches_other_formats(raw):
    text, n = mask_ids(raw)
    assert n == 1 and MASK in text
    assert not any(d in text for d in ("1234567", "30769", "0123456"))


def test_mask_ids_leaves_ordinary_numbers_alone():
    for raw in ("Suit No 1234 of 2010 and CA 14/2000", "paid $1,234,567 in 2001", "Finance 12345"):
        assert mask_ids(raw) == (raw, 0)


def test_build_row_from_unnumbered_page():
    rec = {"slug": "2000_SGCA_3", "citation": "[2000] SGCA 3", "year": 2000,
           "title": "GOH KIM SENG v PUBLIC PROSECUTOR", "fetched_at": "2026-11-03"}
    row = build_row(rec, (FIX / "elit_legacy_unnumbered.html").read_text())
    assert row["citation"] == "[2000] SGCA 3" and row["paragraphs_numbered"] is False
    assert row["source_url"].endswith("/gd/s/2000_SGCA_3")
    assert not row["text"].startswith("[1]")  # no invented paragraph numbers


def test_build_row_masks_ids_in_case_title():
    rec = {"slug": "2000_SGCA_3", "citation": "[2000] SGCA 3", "year": 2000,
           "title": "ONG (EXECUTOR OF THE ESTATE OF TAN (NRIC NO. S1234567A)) v LIM"}
    row = build_row(rec, (FIX / "elit_legacy_unnumbered.html").read_text())
    assert "1234567" not in row["case_name"] and row["ids_masked"] == 1


class FakeApi:
    def __init__(self, private_states):
        self.states = iter(private_states)
        self.uploaded = False
        self.create_kwargs = None

    def create_repo(self, repo, **kw):
        self.create_kwargs = kw

    def repo_info(self, repo, **kw):
        return SimpleNamespace(private=next(self.states))

    def upload_folder(self, **kw):
        self.uploaded = True


def test_upload_creates_private_repo(tmp_path):
    api = FakeApi([True, True])
    assert upload(tmp_path, "me/data", api=api).endswith("/datasets/me/data")
    assert api.uploaded and api.create_kwargs["private"] is True


def test_upload_refuses_existing_public_repo(tmp_path):
    api = FakeApi([False])
    with pytest.raises(PublicRepoError):
        upload(tmp_path, "me/data", api=api)
    assert not api.uploaded


# ---------------------------------------------------------- page-sized subset

def _para(n, words):
    return {"number": n, "text": " ".join(f"w{n}x{i}" for i in range(words)) + "."}


def test_matches_category_handles_dash_and_case_variants():
    assert matches_category(["Tort \u2014 Negligence \u2014 Duty of care"], "Tort \u2014 Negligence")
    assert matches_category(["tort - negligence"], "Tort \u2014 Negligence")
    assert not matches_category(["Tort \u2014 Conspiracy"], "Tort \u2014 Negligence")
    assert not matches_category(["Negligence \u2014 Tort"], "Tort \u2014 Negligence")


def test_select_judgments_prefers_primary_tag_and_skips_unnumbered_and_overshoot():
    cat = "Tort \u2014 Negligence"
    mk = lambda slug, year, tags, words, numbered=True: {
        "slug": slug, "year": year, "catchwords": tags, "paragraphs_numbered": numbered,
        "paragraphs": [_para(1, words)]}
    rows = [
        mk("secondary", 2026, ["Contract", cat], 400),
        mk("primary_old", 2010, [cat], 500),
        mk("too_big", 2026, [cat], 5000),
        mk("unnumbered", 2026, [cat], 300, numbered=False),
        mk("other", 2026, ["Contract"], 300),
        mk("too_short", 2026, [cat], 50),
    ]
    assert [r["slug"] for r in select_judgments(rows, cat, 1000, 100)] == ["primary_old", "secondary"]


def test_allocate_parts_sums_exactly_and_never_gives_zero():
    parts = allocate_parts([3000, 3100, 301, 3599], 33)
    assert sum(parts) == 33 and min(parts) >= 1


def test_segment_paragraphs_is_lossless_with_correct_pinpoints():
    paras = [_para(1, 250), _para(2, 40), _para(5, 700), _para(6, 11)]
    segs = segment_paragraphs(paras, 3)
    assert len(segs) == 3
    source = " ".join(p["text"] for p in paras).split()
    assert " ".join(s["text"] for s in segs).split() == source  # nothing lost or reordered
    assert all(s["word_count"] == len(s["text"].split()) > 0 for s in segs)
    assert segs[0]["para_start"] == 1 and segs[-1]["para_end"] == 6
    for s in segs:  # each piece's first word really comes from its para_start
        assert s["text"].split()[0].startswith(f"w{s['para_start']}x")
        assert s["text"].split()[-1].startswith(f"w{s['para_end']}x")
    assert segs[0]["text"].split()[-1].endswith(".")  # a paragraph end near the target wins

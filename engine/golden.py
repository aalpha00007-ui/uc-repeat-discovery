"""Golden set: 20 posts, chosen blind and stratified by source, that YOU label
by hand. The dashboard then reports agreement and Cohen's kappa per field.

`python run.py golden` writes data/golden_set_to_label.xlsx with drop-downs.
Fill the 'hand_' columns (AI labels are not shown, so the labelling stays
blind), save the file as data/golden_labels.xlsx, and redeploy.
"""
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .analysis import GOLDEN_FIELDS
from .config import CODEBOOK

FIELD_VALUES = {f: CODEBOOK[f]["values"] for f in GOLDEN_FIELDS if f in CODEBOOK}
FIELD_VALUES["primary_theme"] = CODEBOOK["themes"]["values"]


def pick(df: pd.DataFrame, n: int = 20, seed: int = 42) -> pd.DataFrame:
    pool = df[df["passed"]].copy()
    counts = pool["source"].value_counts()
    alloc = (counts / counts.sum() * n).round().astype(int).clip(lower=1)
    alloc = alloc[counts >= 5]
    while alloc.sum() > n:
        alloc[alloc.idxmax()] -= 1
    while alloc.sum() < n:
        alloc[alloc.idxmax()] += 1
    parts = [pool[pool["source"] == s].sample(k, random_state=seed) for s, k in alloc.items() if k > 0]
    return pd.concat(parts).sample(frac=1, random_state=seed)[["record_id", "source", "link", "text"]]


def write_template(gs: pd.DataFrame, path: str):
    wb = Workbook()
    ws = wb.active
    ws.title = "Label these"
    cols = ["record_id", "source", "link", "text"] + [f"hand_{f}" for f in GOLDEN_FIELDS]
    ws.append(cols)
    for r in gs.itertuples():
        ws.append([r.record_id, r.source, r.link, r.text] + [""] * len(GOLDEN_FIELDS))
    hdr = PatternFill("solid", fgColor="DBEAFE")
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = hdr
    ws.column_dimensions["D"].width = 80
    for row in ws.iter_rows(min_row=2, max_col=4, min_col=4):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    # value lists on a second sheet, drop-downs on each hand_ column
    lists = wb.create_sheet("Allowed values")
    for j, f in enumerate(GOLDEN_FIELDS, start=1):
        lists.cell(row=1, column=j, value=f)
        for i, v in enumerate(FIELD_VALUES[f], start=2):
            lists.cell(row=i, column=j, value=v)
        col_letter = lists.cell(row=1, column=j).column_letter
        dv = DataValidation(type="list", allow_blank=True,
                            formula1=f"='Allowed values'!${col_letter}$2:${col_letter}${len(FIELD_VALUES[f]) + 1}")
        ws.add_data_validation(dv)
        target = ws.cell(row=1, column=4 + j).column_letter
        dv.add(f"{target}2:{target}{len(gs) + 1}")
        ws.column_dimensions[target].width = 26
    ws.freeze_panes = "E2"
    wb.save(path)

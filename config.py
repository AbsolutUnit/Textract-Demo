from pdf2image import convert_from_path
from trp.trp2 import TDocument, TDocumentSchema
from trp import Document
import csv
import fitz
import numpy as np
import cv2
import pdf2image
import json
import sys

f = open('sent_file (3).json')
t_doc = Document(json.load(f))
with open('export.csv', 'w', newline='') as f:
    writer = csv.writer(f, delimiter=',')
    for page in t_doc.pages:
        for table in page.tables:
            for r, row in enumerate(table.rows):
                row_ex = []
                for c, cell in enumerate(row.cells):
                    row_ex.append(cell.text.strip())
                writer.writerow(row_ex)
            writer.writerow([])

doc = fitz.open("sent_file.pdf")
for i in range(len(doc)):
    for img in doc.getPageImageList(i):
        xref = img[0]
        pix = fitz.Pixmap(doc, xref)
        if pix.n < 5:  # this is GRAY or RGB
            pix.writePNG("p%s-%s.png" % (i, xref))
        else:  # CMYK: convert to RGB first
            pix1 = fitz.Pixmap(fitz.csRGB, pix)
            pix1.writePNG("p%s-%s.png" % (i, xref))
            pix1 = None
        pix = None


def zero_runs(a):
    # Create an array that is 1 where a is 0, and pad each end with an extra 0.
    iszero = np.concatenate(([0], np.equal(a, 0).view(np.int8), [0]))
    absdiff = np.abs(np.diff(iszero))
    # Runs start and end where absdiff is 1.
    ranges = np.where(absdiff == 1)[0].reshape(-1, 2)
    return ranges


image = convert_from_path("sent_file.pdf")
for img in image:
    img_ex = cv2.imread(img, cv2.IMREAD_COLOR)
    img_gr = cv2.cvtColor(img_ex, cv2.COLOR_BGR2GRAY)
    img_inv = 255 - img_gr

    row_mean = cv2.reduce(img_inv, 1, cv2.REDUCE_AVG, dtype=cv2.CV_32F).flatten()
    row_gaps = zero_runs(row_mean)
    row_cutpoint = (row_gaps[:, 0] + row_gaps[:, 1] - 1) / 2

    b_boxes = []
    for n, (start, end) in enumerate(zip(row_cutpoint, row_cutpoint[1:])):
        line = img[start:end]
        line_inv = img_inv[start:end]
        col_mean = cv2.reduce(line_inv, 0, cv2.REDUCE_AVG, dtype = cv2.CV_32F).flatten()
        col_gaps = zero_runs(col_mean)
        col_gap_sizes = col_gaps[:, 1] - col_gaps[:, 0]
        col_cutpoint = (col_gaps[:, 0] + col_gaps[:, 1] - 1) / 2

        filt_cuts = col_cutpoint[col_gap_sizes > 5]

        for xstart, xend in zip(filt_cuts, filt_cuts[1:]):
            b_boxes.append((xstart, start), (xend, end))


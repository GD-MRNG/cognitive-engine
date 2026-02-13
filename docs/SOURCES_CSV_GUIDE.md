# Sources CSV Guide

This document defines the schema for `inputs/sources.csv`. This file acts as the primary input for the **SourceCSVLoader** and drives the T-Shaped logic (Breadth vs. Depth) of the research pipeline.

## File Structure

* **Format:** Standard CSV (Comma Separated Values)
* **Encoding:** UTF-8
* **Location:** Default path is `inputs/sources.csv`

---

## Column Definitions

| Column | Required | Type | Description |
| --- | --- | --- | --- |
| **`id`** | ✅ | String / Int | **Unique Identifier**|
| **`name`** | ✅ | String | **Source Name**|
| **`url`** | ✅ | String | **Target URL**|
| **`type`** | ✅ | String | **Source Type (datapoint or analysis)** |
| **`tags`** | ❌ | String | **Metadata Tags. Comma-separated list**|
| **`format`** | ✅ | String | **Extraction Strategy (webpage or youtube)**|

---

## Example CSV

```csv
id,name,url,type,rank,tags,format
1,Geopolitical Economy,https://geopoliticaleconomy.com/,analysis,1,"politics,deep-dive",webpage
2,World Affairs,https://www.youtube.com/@lenapetrova/videos,analysis,1,"politics,video",youtube
3,Channel News Asia,https://www.youtube.com/@channelnewsasia/videos,datapoint,5,"news,asia",youtube
4,SCMP,https://www.scmp.com/,datapoint,5,"news,china",webpage

```

---

## Best Practices

1. **Strict Types:** Ensure the `type` column is exactly **`datapoint`** or **`analysis`**.
* Use **`datapoint`** for high-volume news feeds where you want *headlines* or *latest articles* automatically.
* Use **`analysis`** for sources where you want to *cherry-pick* specific deep-dive articles or videos.

2. **Stable IDs:** Do not reuse IDs. If you remove a source, retire its ID to keep the `research.json` history consistent.

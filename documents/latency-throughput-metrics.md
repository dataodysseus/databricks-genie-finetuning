
## The 5 Key Metrics 

### **1. End-to-End Latency** 
```python
end_to_end_latency
```

**What it is:** Total time from when the user asks a question to when they see the answer.

**Example:** User asks "What are total sales?" at 10:00:00 AM, gets answer at 10:00:47 AM → **47 seconds**

**Why it matters:** This is what your users experience. If this is 60 seconds, users wait 1 minute per question.

**Good target:** < 30 seconds for simple queries, < 60 seconds for complex ones

---

### **2. Total Wait Time** 
```python
total_wait_time
```

**What it is:** Time Genie spends actually processing the query (running SQL, analyzing data).

**Example:** Out of 47 seconds total, 45 seconds is Genie working, 2 seconds is API overhead.

**Why it matters:** This tells you if slowness is Genie's fault (processing) or infrastructure (API/network).

**Comparison:**
- If `total_wait_time` ≈ `end_to_end_latency` → Genie is the bottleneck
- If `total_wait_time` << `end_to_end_latency` → API/network is slow

---

### **3. Rows Per Second** (Throughput)
```python
rows_per_second
```

**What it is:** How fast data is delivered to the user.

**Example:** Query returns 1,000 rows in 50 seconds → **20 rows/second**

**Why it matters:** Indicates if you can handle large result sets efficiently.

**Good target:** 
- Small queries (< 100 rows): Not critical
- Large queries (> 1,000 rows): Want > 50 rows/second

---

### **4. P95 Latency** (95th Percentile)
```python
Calculated in summary: successful_metrics['end_to_end_latency'].quantile(0.95)
```

**What it is:** 95% of queries finish faster than this time.

**Example:** P95 = 60 seconds means only 5% of queries take longer than 60 seconds.

**Why it matters:** 
- Average hides outliers
- P95 shows the "worst normal case"
- Used for SLA guarantees

**Good target:** P95 < 90 seconds (so most users wait less than 1.5 minutes)

---

### **5. Poll Count**
```python
poll_count
```

**What it is:** How many times we checked "is the answer ready yet?"

**Example:** We checked 9 times (every 5 seconds) over 45 seconds.

**Why it matters:** 
- Too many polls = wasting API calls
- Shows if our 5-second polling interval is appropriate

**Good target:** 5-15 polls for typical queries (means 25-75 second processing time)

---

##  Quick Interpretation Guide

### **Scenario 1: Slow for Everyone**
```
End-to-End: 90 seconds (avg)
Wait Time:   88 seconds (avg)
P95:        120 seconds
```
**Diagnosis:** Genie itself is slow (wait time = most of the delay)
**Action:** Optimize queries, check Databricks cluster size

### **Scenario 2: Network/API Issues**
```
End-to-End: 60 seconds (avg)
Wait Time:   40 seconds (avg)
P95:         70 seconds
```
**Diagnosis:** 20 seconds lost to API overhead
**Action:** Check network latency, optimize API calls, reduce polling

### **Scenario 3: Occasional Outliers**
```
End-to-End: 30 seconds (avg)
Wait Time:   28 seconds (avg)
P95:        120 seconds
```
**Diagnosis:** Most queries fast, but 5% are super slow
**Action:** Investigate which query types cause outliers (use "Performance by Use Case" query)

### **Scenario 4: Good Performance**
```
End-to-End: 25 seconds (avg)
Wait Time:   23 seconds (avg)
P95:         40 seconds
```
**Diagnosis:** Fast and consistent! 
**Action:** Nothing, you're doing great

---

##  What to Tell Leadership

Use this simple summary:

> **"Our Genie integration averages X seconds per query (end-to-end latency), with 95% of queries completing in under Y seconds (P95). The system can process Z rows per second (throughput). Most of the time is spent waiting for Genie to process the data (total wait time), not on API overhead."**

**Example:**
> "Our Genie integration averages **35 seconds per query**, with **95% of queries completing in under 55 seconds**. The system can process **45 rows per second**. Most time (33 seconds) is Genie processing, with only 2 seconds of API overhead."

---

##  One-Line Summary for Each Metric

| Metric | What It Tells You |
|--------|-------------------|
| **End-to-End Latency** | User wait time |
| **Total Wait Time** | How long Genie actually works |
| **Rows Per Second** | Data delivery speed |
| **P95 Latency** | Worst-case-that's-still-normal |
| **Poll Count** | API efficiency check |

---

##  Metrics You Can Ignore (For Now)

- `send_message_latency` - Usually < 1 second, not important
- `result_fetch_latency` - Usually < 2 seconds, not important
- `avg_poll_latency` - Just a detail about polling
- `bytes_per_second` - Only matters for HUGE datasets
- `min/max_poll_latency` - Noise, not useful

Focus on the **5 key metrics** above and you'll have everything your leadership needs! 
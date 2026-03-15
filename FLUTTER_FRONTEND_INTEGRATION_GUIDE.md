# 🐄 RSS Dairy — Flutter Frontend Integration Guide

> **Backend**: Django REST Framework on Vercel  
> **Database**: PostgreSQL (Supabase) / SQLite (local dev)  
> **Base URL**: `https://<your-vercel-app>.vercel.app/api`  
> **Auth**: None (all endpoints are open — `AllowAny`)

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Data Models & JSON Shapes](#2-data-models--json-shapes)
3. [Session Management (Start / Stop / Status)](#3-session-management)
4. [Hardware Scan Flow — POST /api/scans/](#4-hardware-scan-flow)
5. [Real-Time Data — Polling vs SSE](#5-real-time-data--polling-vs-sse)
6. [Block & Cow Master Data](#6-block--cow-master-data)
7. [Analytics Endpoints](#7-analytics-endpoints)
8. [Complete Flutter Integration Code](#8-complete-flutter-integration-code)
9. [State Management Recommendations](#9-state-management-recommendations)
10. [Error Handling & Edge Cases](#10-error-handling--edge-cases)

---

## 1. Architecture Overview

```
┌──────────────────┐     POST /api/scans/     ┌──────────────────────────┐
│  RFID Hardware   │ ──────────────────────▶  │   Django REST Backend    │
│  (Raspberry Pi)  │                          │   (Vercel Serverless)    │
└──────────────────┘                          │                          │
                                              │  ┌──────────────────┐   │
                                              │  │   ScanSession    │   │
                                              │  │  (active block)  │   │
                                              │  └──────────────────┘   │
                                              │  ┌──────────────────┐   │
┌──────────────────┐    GET /api/scans/       │  │   RfidScan       │   │
│  Flutter App     │ ◀────── (polling) ──────│  │   (scan logs)    │   │
│  (Mobile / Web)  │                          │  └──────────────────┘   │
│                  │    GET /api/stream/       │  ┌──────────────────┐   │
│                  │ ◀────── (SSE) ──────────│  │   Cow / Block    │   │
└──────────────────┘                          │  │   (master data)  │   │
                                              └──────────────────────────┘
```

### Flow Summary

1. **Flutter app starts a session** → `POST /api/session/` with `action: "start"` and a `block` name.
2. **Hardware (Raspberry Pi)** continuously pushes RFID tag data → `POST /api/scans/`.
3. **Backend** checks if a session is active. If yes, it saves the scan and broadcasts it; if no, it **silently ignores** the scan.
4. **Flutter app receives data** via **short polling** (`GET /api/scans/`) or **SSE** (`GET /api/stream/`).
5. **Flutter app stops the session** → `POST /api/session/` with `action: "stop"`.

---

## 2. Data Models & JSON Shapes

### 2.1 Block

| Field  | Type   | Description              |
|--------|--------|--------------------------|
| `id`   | int    | Auto-generated PK        |
| `name` | string | Unique block name (e.g. `"A"`, `"B"`, `"North Shed"`) |

```json
{ "id": 1, "name": "A" }
```

### 2.2 Cow

| Field             | Type      | Description                              |
|-------------------|-----------|------------------------------------------|
| `id`              | int       | Auto-generated PK                        |
| `uid`             | string    | Unique RFID tag ID                       |
| `name`            | string    | Cow's name                               |
| `last_seen_block` | int/null  | FK → Block ID (last scanned block)       |
| `last_seen_time`  | datetime/null | Last scan timestamp                  |

```json
{
  "id": 5,
  "uid": "A1B2C3D4",
  "name": "Lakshmi",
  "last_seen_block": 1,
  "last_seen_time": "2026-03-15T10:30:00"
}
```

### 2.3 ScanSession

| Field          | Type     | Description                        |
|----------------|----------|------------------------------------|
| `id`           | int      | Auto-generated PK                  |
| `active_block` | int      | FK → Block                         |
| `start_time`   | datetime | Auto-set on creation               |
| `is_active`    | bool     | `true` = session is live           |

> **Important**: Only ONE session should be active at a time. Starting a new session automatically deactivates any previous active session.

### 2.4 RfidScan (the core scan record)

| Field        | Type   | Description                                   |
|--------------|--------|-----------------------------------------------|
| `id`         | int    | Auto-generated PK                             |
| `uid`        | string | RFID tag UID                                  |
| `name`       | string | Cow name (defaults to `"Unknown"`)            |
| `block`      | string | Block name (forced from active session)       |
| `direction`  | string | `"IN"` or `"OUT"` (auto-toggled by backend)   |
| `time`       | time   | Scan time from device (`HH:MM:SS`)            |
| `date`       | date   | Scan date from device (`YYYY-MM-DD`)          |
| `updated_at` | datetime | Server-side auto timestamp                  |

```json
{
  "id": 42,
  "uid": "A1B2C3D4",
  "name": "Lakshmi",
  "block": "A",
  "direction": "OUT",
  "time": "14:30:25",
  "date": "2026-03-15",
  "updated_at": "2026-03-15T09:00:25.123456Z"
}
```

**Direction Logic** (handled by backend, read-only for frontend):
- First scan of the day for a UID → `"OUT"` (cow is going out)
- Subsequent scans toggle: `OUT → IN → OUT → IN ...`

---

## 3. Session Management

> **⚠️ Critical**: Scans from hardware are **silently ignored** if no session is active. The Flutter app **must** start a session before any scans will be recorded.

### 3.1 Get Current Session Status

```
GET /api/session/
```

**Response when active:**
```json
{
  "is_active": true,
  "block": "A",
  "start_time": "2026-03-15 10:00:00.123456+00:00"
}
```

**Response when inactive:**
```json
{
  "is_active": false,
  "block": null
}
```

### 3.2 Start a Session

```
POST /api/session/
Content-Type: application/json

{
  "action": "start",
  "block": "A"
}
```

**Response (200):**
```json
{ "message": "Session started for A" }
```

**Error — missing block (400):**
```json
{ "error": "Block name required" }
```

> **Note**: Starting a session automatically **deactivates** any previously active session. You do NOT need to stop the old one first.

### 3.3 Stop a Session

```
POST /api/session/
Content-Type: application/json

{
  "action": "stop"
}
```

**Response (200):**
```json
{ "message": "Session stopped" }
```

### 3.4 Flutter Dart Code — Session Service

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

class SessionService {
  static const String baseUrl = 'https://<YOUR_VERCEL_APP>.vercel.app/api';

  /// Check if a scanning session is currently active
  static Future<Map<String, dynamic>> getSessionStatus() async {
    final response = await http.get(Uri.parse('$baseUrl/session/'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to get session status: ${response.statusCode}');
  }

  /// Start a new scanning session for a specific block
  /// [blockName] — e.g. "A", "B", "North Shed"
  static Future<Map<String, dynamic>> startSession(String blockName) async {
    final response = await http.post(
      Uri.parse('$baseUrl/session/'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'action': 'start',
        'block': blockName,
      }),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to start session: ${response.body}');
  }

  /// Stop the currently active scanning session
  static Future<Map<String, dynamic>> stopSession() async {
    final response = await http.post(
      Uri.parse('$baseUrl/session/'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'action': 'stop'}),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to stop session: ${response.body}');
  }
}
```

---

## 4. Hardware Scan Flow

### How It Works (For Frontend Developer's Understanding)

This is **NOT called by the Flutter app** — it is called by the RFID hardware (Raspberry Pi). But you need to understand it because the data it produces is what you display.

```
POST /api/scans/
Content-Type: application/json

{
  "uid":  "A1B2C3D4",
  "name": "Lakshmi",
  "date": "2026-03-15",
  "time": "14:30:25"
}
```

**What the backend does:**
1. Checks if a session is active → if not, returns `{"message": "Scan ignored (No active session)"}` with `200 OK`.
2. Validates `uid`, `date`, `time` → errors if missing/invalid.
3. Determines direction (`IN`/`OUT`) by checking the last scan for this UID on the same day.
4. Forces the `block` field from the active session's block (ignores any block sent by hardware).
5. Auto-creates a `Cow` record if this UID hasn't been seen before.
6. Updates the cow's `last_seen_block` and `last_seen_time`.
7. Saves a new `RfidScan` row.
8. **Broadcasts** the scan to all SSE listeners (this is how real-time streaming works).
9. Returns the created scan as JSON with `201 Created`.

**Response (201):**
```json
{
  "id": 42,
  "uid": "A1B2C3D4",
  "name": "Lakshmi",
  "block": "A",
  "direction": "OUT",
  "time": "14:30:25",
  "date": "2026-03-15",
  "updated_at": "2026-03-15T09:00:25.123456Z"
}
```

---

## 5. Real-Time Data — Polling vs SSE

You have **two options** to receive live scan data in the Flutter app. Here's when to use each:

| Approach       | Best For                          | Limitation                                    |
|----------------|-----------------------------------|-----------------------------------------------|
| **Short Polling** | Vercel deployment, reliability | Slight delay (poll interval), more HTTP calls |
| **SSE Stream** | Self-hosted server, true real-time | ❌ Breaks on Vercel (serverless function timeout) |

> **⚠️ Recommendation**: Use **short polling** if deploying to Vercel. SSE will time out on Vercel's serverless functions (max 10-25s execution).

---

### 5.1 Option A: Short Polling (✅ Recommended for Vercel)

Poll `GET /api/scans/` every 2–5 seconds to fetch the latest scan records.

```
GET /api/scans/
```

**Response (200):** Array of all scans, ordered by most recent first:
```json
[
  {
    "id": 42,
    "uid": "A1B2C3D4",
    "name": "Lakshmi",
    "block": "A",
    "direction": "OUT",
    "time": "14:30:25",
    "date": "2026-03-15",
    "updated_at": "2026-03-15T09:00:25.123456Z"
  },
  ...
]
```

#### Flutter Dart Code — Polling Service

```dart
import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

class ScanPollingService {
  static const String baseUrl = 'https://<YOUR_VERCEL_APP>.vercel.app/api';

  Timer? _timer;
  final Function(List<Map<String, dynamic>>) onDataReceived;
  final Duration interval;
  int _lastKnownId = 0;

  ScanPollingService({
    required this.onDataReceived,
    this.interval = const Duration(seconds: 3),
  });

  /// Start polling for new scans
  void start() {
    // Fetch immediately first, then set up timer
    _fetchScans();
    _timer = Timer.periodic(interval, (_) => _fetchScans());
  }

  /// Stop polling
  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> _fetchScans() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/scans/'));
      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        final scans = data.cast<Map<String, dynamic>>();

        // Filter only new scans (id > last known)
        final newScans = scans.where((s) => (s['id'] as int) > _lastKnownId).toList();

        if (newScans.isNotEmpty) {
          _lastKnownId = newScans
              .map((s) => s['id'] as int)
              .reduce((a, b) => a > b ? a : b);
          onDataReceived(newScans);
        }
      }
    } catch (e) {
      print('Polling error: $e');
    }
  }
}
```

**Usage in a Widget:**

```dart
class LiveScanScreen extends StatefulWidget {
  @override
  _LiveScanScreenState createState() => _LiveScanScreenState();
}

class _LiveScanScreenState extends State<LiveScanScreen> {
  late ScanPollingService _poller;
  List<Map<String, dynamic>> _scans = [];

  @override
  void initState() {
    super.initState();
    _poller = ScanPollingService(
      onDataReceived: (newScans) {
        setState(() {
          _scans.insertAll(0, newScans); // Insert new scans at the top
        });
      },
      interval: const Duration(seconds: 3),
    );
    _poller.start();
  }

  @override
  void dispose() {
    _poller.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: _scans.length,
      itemBuilder: (context, index) {
        final scan = _scans[index];
        return ListTile(
          leading: Icon(
            scan['direction'] == 'OUT' ? Icons.arrow_upward : Icons.arrow_downward,
            color: scan['direction'] == 'OUT' ? Colors.red : Colors.green,
          ),
          title: Text('${scan['name']} (${scan['uid']})'),
          subtitle: Text('Block ${scan['block']} • ${scan['direction']} • ${scan['time']}'),
          trailing: Text(scan['date']),
        );
      },
    );
  }
}
```

---

### 5.2 Option B: SSE Stream (For Self-Hosted Servers Only)

```
GET /api/stream/
Accept: text/event-stream
```

The server sends Server-Sent Events. Each event's `data:` field contains a JSON scan object:

```
: connected

data: {"id":42,"uid":"A1B2C3D4","name":"Lakshmi","block":"A","direction":"OUT","time":"14:30:25","date":"2026-03-15","updated_at":"2026-03-15T09:00:25.123456Z"}

: ping 1710518425
```

- Lines starting with `:` are comments (connection confirmation / heartbeat pings every 10 seconds).
- Lines starting with `data:` contain the actual scan JSON.

#### Flutter Dart Code — SSE Client

Add the `flutter_client_sse` or `eventsource` package to `pubspec.yaml`:

```yaml
dependencies:
  http: ^1.2.0
  # For SSE support:
  eventsource: ^0.4.0
```

```dart
import 'dart:convert';
import 'package:eventsource/eventsource.dart';

class ScanStreamService {
  static const String streamUrl = 'https://<YOUR_SERVER>/api/stream/';

  EventSource? _eventSource;
  final Function(Map<String, dynamic>) onScanReceived;

  ScanStreamService({required this.onScanReceived});

  /// Connect to the SSE stream
  Future<void> connect() async {
    _eventSource = await EventSource.connect(streamUrl);

    _eventSource!.listen((Event event) {
      if (event.data != null && event.data!.isNotEmpty) {
        try {
          final scanData = jsonDecode(event.data!);
          onScanReceived(scanData);
        } catch (e) {
          print('SSE parse error: $e');
        }
      }
    });
  }

  /// Disconnect from the SSE stream
  void disconnect() {
    _eventSource?.close();
    _eventSource = null;
  }
}
```

---

## 6. Block & Cow Master Data

### 6.1 List All Blocks

```
GET /api/blocks/
```

**Response (200):**
```json
[
  { "id": 1, "name": "A" },
  { "id": 2, "name": "B" }
]
```

### 6.2 Create a Block

```
POST /api/blocks/
Content-Type: application/json

{ "name": "C" }
```

**Response (201):**
```json
{ "id": 3, "name": "C" }
```

### 6.3 List All Cows

```
GET /api/cows/
```

**Response (200):**
```json
[
  {
    "id": 1,
    "uid": "A1B2C3D4",
    "name": "Lakshmi",
    "last_seen_block": 1,
    "last_seen_time": "2026-03-15T10:30:00Z"
  }
]
```

### 6.4 Register Cows (Single or Bulk)

**Single:**
```
POST /api/cows/
Content-Type: application/json

{ "uid": "XXYY1234", "name": "Gauri" }
```

**Bulk (array):**
```
POST /api/cows/
Content-Type: application/json

[
  { "uid": "XXYY1234", "name": "Gauri" },
  { "uid": "AABB5678", "name": "Nandi" }
]
```

#### Flutter Dart Code — Master Data Service

```dart
class MasterDataService {
  static const String baseUrl = 'https://<YOUR_VERCEL_APP>.vercel.app/api';

  /// Fetch all blocks
  static Future<List<Map<String, dynamic>>> getBlocks() async {
    final response = await http.get(Uri.parse('$baseUrl/blocks/'));
    if (response.statusCode == 200) {
      return List<Map<String, dynamic>>.from(jsonDecode(response.body));
    }
    throw Exception('Failed to load blocks');
  }

  /// Create a new block
  static Future<Map<String, dynamic>> createBlock(String name) async {
    final response = await http.post(
      Uri.parse('$baseUrl/blocks/'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
    if (response.statusCode == 201) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to create block: ${response.body}');
  }

  /// Fetch all registered cows
  static Future<List<Map<String, dynamic>>> getCows() async {
    final response = await http.get(Uri.parse('$baseUrl/cows/'));
    if (response.statusCode == 200) {
      return List<Map<String, dynamic>>.from(jsonDecode(response.body));
    }
    throw Exception('Failed to load cows');
  }

  /// Register cows (single or bulk)
  static Future<dynamic> registerCows(List<Map<String, String>> cows) async {
    final body = cows.length == 1 ? jsonEncode(cows.first) : jsonEncode(cows);
    final response = await http.post(
      Uri.parse('$baseUrl/cows/'),
      headers: {'Content-Type': 'application/json'},
      body: body,
    );
    if (response.statusCode == 201) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to register cows: ${response.body}');
  }
}
```

---

## 7. Analytics Endpoints

### 7.1 Missing Cows

Returns cows with an **odd number of scans** on a given date (meaning they went OUT but never came back IN).

```
GET /api/missing-cows/?date=2026-03-15
```

> `date` is optional — defaults to today.

**Response (200):**
```json
{
  "date": "2026-03-15",
  "missing_count": 2,
  "missing_cows": [
    { "uid": "A1B2C3D4", "name": "Lakshmi", "scan_count": 3 },
    { "uid": "E5F6G7H8", "name": "Gauri",   "scan_count": 1 }
  ]
}
```

### 7.2 Attendance Summary

Full attendance breakdown per cow for a given date.

```
GET /api/attendance-summary/?date=2026-03-15
```

> `date` is optional — defaults to today.

**Response (200):**
```json
{
  "date": "2026-03-15",
  "count": 3,
  "attendance": [
    {
      "uid": "A1B2C3D4",
      "name": "Lakshmi",
      "total_scans": 4,
      "out_scans": 2,
      "in_scans": 2,
      "outside": false
    },
    {
      "uid": "E5F6G7H8",
      "name": "Gauri",
      "total_scans": 1,
      "out_scans": 1,
      "in_scans": 0,
      "outside": true
    }
  ]
}
```

#### Flutter Dart Code — Analytics Service

```dart
class AnalyticsService {
  static const String baseUrl = 'https://<YOUR_VERCEL_APP>.vercel.app/api';

  /// Get missing cows for a date (null = today)
  static Future<Map<String, dynamic>> getMissingCows({String? date}) async {
    final query = date != null ? '?date=$date' : '';
    final response = await http.get(Uri.parse('$baseUrl/missing-cows/$query'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to load missing cows');
  }

  /// Get attendance summary for a date (null = today)
  static Future<Map<String, dynamic>> getAttendanceSummary({String? date}) async {
    final query = date != null ? '?date=$date' : '';
    final response = await http.get(Uri.parse('$baseUrl/attendance-summary/$query'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    }
    throw Exception('Failed to load attendance summary');
  }
}
```

---

## 8. Complete Flutter Integration Code

### 8.1 Complete API Client (`api_client.dart`)

```dart
import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

/// Central API client for the RSS Dairy RFID Backend.
/// Replace BASE_URL with your actual deployment URL.
class RssDairyApi {
  static const String BASE_URL = 'https://<YOUR_VERCEL_APP>.vercel.app/api';

  // ─────────── SESSION ───────────

  static Future<SessionStatus> getSessionStatus() async {
    final res = await http.get(Uri.parse('$BASE_URL/session/'));
    final body = jsonDecode(res.body);
    return SessionStatus(
      isActive: body['is_active'] ?? false,
      block: body['block'],
      startTime: body['start_time'],
    );
  }

  static Future<void> startSession(String blockName) async {
    await http.post(
      Uri.parse('$BASE_URL/session/'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'action': 'start', 'block': blockName}),
    );
  }

  static Future<void> stopSession() async {
    await http.post(
      Uri.parse('$BASE_URL/session/'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'action': 'stop'}),
    );
  }

  // ─────────── SCANS ───────────

  static Future<List<ScanRecord>> fetchScans() async {
    final res = await http.get(Uri.parse('$BASE_URL/scans/'));
    final List<dynamic> data = jsonDecode(res.body);
    return data.map((e) => ScanRecord.fromJson(e)).toList();
  }

  // ─────────── BLOCKS ───────────

  static Future<List<BlockItem>> fetchBlocks() async {
    final res = await http.get(Uri.parse('$BASE_URL/blocks/'));
    final List<dynamic> data = jsonDecode(res.body);
    return data.map((e) => BlockItem.fromJson(e)).toList();
  }

  static Future<BlockItem> createBlock(String name) async {
    final res = await http.post(
      Uri.parse('$BASE_URL/blocks/'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'name': name}),
    );
    return BlockItem.fromJson(jsonDecode(res.body));
  }

  // ─────────── COWS ───────────

  static Future<List<CowItem>> fetchCows() async {
    final res = await http.get(Uri.parse('$BASE_URL/cows/'));
    final List<dynamic> data = jsonDecode(res.body);
    return data.map((e) => CowItem.fromJson(e)).toList();
  }

  // ─────────── ANALYTICS ───────────

  static Future<MissingCowsReport> fetchMissingCows({String? date}) async {
    final q = date != null ? '?date=$date' : '';
    final res = await http.get(Uri.parse('$BASE_URL/missing-cows/$q'));
    return MissingCowsReport.fromJson(jsonDecode(res.body));
  }

  static Future<AttendanceReport> fetchAttendanceSummary({String? date}) async {
    final q = date != null ? '?date=$date' : '';
    final res = await http.get(Uri.parse('$BASE_URL/attendance-summary/$q'));
    return AttendanceReport.fromJson(jsonDecode(res.body));
  }
}

// ─────────── DATA MODELS ───────────

class SessionStatus {
  final bool isActive;
  final String? block;
  final String? startTime;
  SessionStatus({required this.isActive, this.block, this.startTime});
}

class ScanRecord {
  final int id;
  final String uid;
  final String name;
  final String block;
  final String direction;
  final String time;
  final String date;
  final String updatedAt;

  ScanRecord({
    required this.id,
    required this.uid,
    required this.name,
    required this.block,
    required this.direction,
    required this.time,
    required this.date,
    required this.updatedAt,
  });

  factory ScanRecord.fromJson(Map<String, dynamic> json) => ScanRecord(
    id: json['id'],
    uid: json['uid'] ?? '',
    name: json['name'] ?? 'Unknown',
    block: json['block'] ?? '',
    direction: json['direction'] ?? 'OUT',
    time: json['time'] ?? '',
    date: json['date'] ?? '',
    updatedAt: json['updated_at'] ?? '',
  );

  bool get isOut => direction == 'OUT';
  bool get isIn => direction == 'IN';
}

class BlockItem {
  final int id;
  final String name;
  BlockItem({required this.id, required this.name});
  factory BlockItem.fromJson(Map<String, dynamic> json) =>
      BlockItem(id: json['id'], name: json['name']);
}

class CowItem {
  final int id;
  final String uid;
  final String name;
  final int? lastSeenBlock;
  final String? lastSeenTime;

  CowItem({
    required this.id,
    required this.uid,
    required this.name,
    this.lastSeenBlock,
    this.lastSeenTime,
  });

  factory CowItem.fromJson(Map<String, dynamic> json) => CowItem(
    id: json['id'],
    uid: json['uid'],
    name: json['name'],
    lastSeenBlock: json['last_seen_block'],
    lastSeenTime: json['last_seen_time'],
  );
}

class MissingCowsReport {
  final String date;
  final int missingCount;
  final List<Map<String, dynamic>> missingCows;

  MissingCowsReport({
    required this.date,
    required this.missingCount,
    required this.missingCows,
  });

  factory MissingCowsReport.fromJson(Map<String, dynamic> json) =>
      MissingCowsReport(
        date: json['date'].toString(),
        missingCount: json['missing_count'],
        missingCows: List<Map<String, dynamic>>.from(json['missing_cows']),
      );
}

class AttendanceReport {
  final String date;
  final int count;
  final List<Map<String, dynamic>> attendance;

  AttendanceReport({
    required this.date,
    required this.count,
    required this.attendance,
  });

  factory AttendanceReport.fromJson(Map<String, dynamic> json) =>
      AttendanceReport(
        date: json['date'].toString(),
        count: json['count'],
        attendance: List<Map<String, dynamic>>.from(json['attendance']),
      );
}
```

### 8.2 Polling Manager with Auto-Reconnect

```dart
/// A robust polling manager that handles errors gracefully
/// and provides stream-like interface for UI consumption.
class ScanPollingManager {
  static const String baseUrl = 'https://<YOUR_VERCEL_APP>.vercel.app/api';

  Timer? _timer;
  final StreamController<List<ScanRecord>> _controller =
      StreamController<List<ScanRecord>>.broadcast();
  int _lastKnownId = 0;
  bool _isPolling = false;
  int _consecutiveErrors = 0;

  /// Stream of new scans — subscribe to this in your UI
  Stream<List<ScanRecord>> get scanStream => _controller.stream;
  bool get isPolling => _isPolling;

  /// Start polling with adaptive interval
  /// Slows down on errors, speeds up on success
  void start({Duration interval = const Duration(seconds: 3)}) {
    if (_isPolling) return;
    _isPolling = true;
    _consecutiveErrors = 0;
    _poll(); // Immediately fetch
    _timer = Timer.periodic(interval, (_) => _poll());
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
    _isPolling = false;
  }

  void dispose() {
    stop();
    _controller.close();
  }

  Future<void> _poll() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/scans/'))
          .timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        _consecutiveErrors = 0;
        final List<dynamic> data = jsonDecode(response.body);
        final scans = data.map((e) => ScanRecord.fromJson(e)).toList();
        final newScans = scans.where((s) => s.id > _lastKnownId).toList();

        if (newScans.isNotEmpty) {
          _lastKnownId = newScans.map((s) => s.id).reduce((a, b) => a > b ? a : b);
          _controller.add(newScans);
        }
      }
    } catch (e) {
      _consecutiveErrors++;
      print('Poll error (#$_consecutiveErrors): $e');
      // After 5 consecutive errors, notify the UI
      if (_consecutiveErrors >= 5) {
        _controller.addError('Connection lost. Retrying...');
      }
    }
  }
}
```

---

## 9. State Management Recommendations

### Recommended Flutter Architecture

```
                     ┌──────────────────────┐
                     │   App (MaterialApp)   │
                     └──────────┬───────────┘
                                │
                   ┌────────────▼────────────┐
                   │   Provider / Riverpod   │
                   │   (State Management)    │
                   └────────────┬────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
  ┌─────────────────┐ ┌────────────────┐ ┌──────────────────┐
  │ SessionProvider  │ │  ScanProvider  │ │ AnalyticsProvider│
  │ - isActive       │ │ - liveScans    │ │ - missingCows    │
  │ - activeBlock    │ │ - pollingMgr   │ │ - attendance     │
  │ - start/stop()   │ │ - start/stop() │ │ - fetch()        │
  └─────────────────┘ └────────────────┘ └──────────────────┘
```

### Example with `ChangeNotifier` (Provider)

```dart
class SessionProvider extends ChangeNotifier {
  bool _isActive = false;
  String? _activeBlock;

  bool get isActive => _isActive;
  String? get activeBlock => _activeBlock;

  Future<void> checkStatus() async {
    final status = await RssDairyApi.getSessionStatus();
    _isActive = status.isActive;
    _activeBlock = status.block;
    notifyListeners();
  }

  Future<void> startSession(String block) async {
    await RssDairyApi.startSession(block);
    _isActive = true;
    _activeBlock = block;
    notifyListeners();
  }

  Future<void> stopSession() async {
    await RssDairyApi.stopSession();
    _isActive = false;
    _activeBlock = null;
    notifyListeners();
  }
}
```

```dart
class ScanProvider extends ChangeNotifier {
  final ScanPollingManager _poller = ScanPollingManager();
  List<ScanRecord> _scans = [];

  List<ScanRecord> get scans => _scans;

  void startPolling() {
    _poller.scanStream.listen((newScans) {
      _scans.insertAll(0, newScans);
      notifyListeners();
    });
    _poller.start();
  }

  void stopPolling() {
    _poller.stop();
  }

  @override
  void dispose() {
    _poller.dispose();
    super.dispose();
  }
}
```

---

## 10. Error Handling & Edge Cases

### Common Error Responses

| Scenario                              | HTTP Status | Response Body                                    |
|---------------------------------------|-------------|--------------------------------------------------|
| Scan with no active session           | `200`       | `{"message": "Scan ignored (No active session)"}`|
| Missing `uid` in scan                 | `400`       | `{"error": "uid is required"}`                   |
| Invalid date/time format              | `400`       | `{"error": "Invalid date/time format"}`          |
| Missing block when starting session   | `400`       | `{"error": "Block name required"}`               |
| Invalid action on session endpoint    | `400`       | `{"error": "Invalid action"}`                    |

### Edge Cases to Handle in Flutter

1. **Session already active**: Starting a new session silently stops the old one. No error is thrown. Your UI should reflect the new block.
2. **No scans yet**: `GET /api/scans/` returns `[]`. Handle empty state gracefully.
3. **Same cow scanned rapidly**: Each scan creates a separate row with toggling direction. The UI should show all entries.
4. **Date boundaries**: Direction resets when the date changes. A cow that was `IN` yesterday starts as `OUT` today.
5. **Network timeouts**: Implement retry logic with exponential backoff. The `ScanPollingManager` above handles this.
6. **Vercel cold starts**: First request after inactivity may take 2-5 seconds. Show a loading indicator.

### Recommended `pubspec.yaml` Dependencies

```yaml
dependencies:
  flutter:
    sdk: flutter
  http: ^1.2.0              # HTTP client
  provider: ^6.1.0          # State management (or use riverpod)
  intl: ^0.19.0             # Date/time formatting
  # Only if using SSE (self-hosted):
  # eventsource: ^0.4.0
```

---

## Quick Reference — All Endpoints

| Method | Endpoint                  | Purpose                        | Called By       |
|--------|---------------------------|--------------------------------|-----------------|
| `GET`  | `/api/session/`           | Check active session           | Flutter App     |
| `POST` | `/api/session/`           | Start/Stop session             | Flutter App     |
| `GET`  | `/api/scans/`             | List all scans (polling)       | Flutter App     |
| `POST` | `/api/scans/`             | Submit a new scan              | **Hardware**    |
| `GET`  | `/api/scans/<id>/`        | Get single scan detail         | Flutter App     |
| `PUT`  | `/api/scans/<id>/`        | Update a scan                  | Flutter App     |
| `DELETE`| `/api/scans/<id>/`       | Delete a scan                  | Flutter App     |
| `GET`  | `/api/stream/`            | SSE real-time stream           | Flutter App     |
| `GET`  | `/api/blocks/`            | List all blocks                | Flutter App     |
| `POST` | `/api/blocks/`            | Create a block                 | Flutter App     |
| `GET`  | `/api/cows/`              | List all cows                  | Flutter App     |
| `POST` | `/api/cows/`              | Register cow(s)                | Flutter App     |
| `GET`  | `/api/missing-cows/`      | Cows still outside             | Flutter App     |
| `GET`  | `/api/attendance-summary/`| Full attendance breakdown      | Flutter App     |

---

*Generated on 2026-03-15 from codebase analysis of `RSS_COWRFID_BACKEND`*

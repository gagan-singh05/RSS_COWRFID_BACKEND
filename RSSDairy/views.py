
# from rest_framework import generics, status
# from rest_framework.response import Response
# from rest_framework.permissions import AllowAny
# from .models import RfidScan
# from .serializers import RfidScanSerializer
# from RSSDairy.sse import broadcaster

# class RfidScanListCreate(generics.ListCreateAPIView):
#     serializer_class = RfidScanSerializer
#     queryset = RfidScan.objects.all().order_by("-updated_at")
#     authentication_classes: list = []      # ✅ no session/JWT -> no CSRF
#     permission_classes = [AllowAny]

#     def create(self, request, *args, **kwargs):
#         uid = request.data.get("uid")
#         instance = RfidScan.objects.filter(uid=uid).first() if uid else None
#         serializer = self.get_serializer(instance=instance, data=request.data)
#         serializer.is_valid(raise_exception=True)

#         # Determine block from name mapping: 'desh' -> 'A', 'bholu' -> 'B'
#         name_val = serializer.validated_data.get("name") or request.data.get("name")
#         block_override = None
#         if name_val:
#             try:
#                 name_clean = str(name_val).strip().lower()
#             except Exception:
#                 name_clean = ""
#             if name_clean == "desh":
#                 block_override = "A"
#             elif name_clean == "bholu":
#                 block_override = "B"

#         # If we determined a block, pass it to save() to enforce the mapping.
#         if block_override is not None:
#             obj = serializer.save(block=block_override)
#         else:
#             obj = serializer.save()
#         out = RfidScanSerializer(obj).data
#         try:
#             broadcaster.publish(out)
#         except Exception:
#             pass
#         return Response(out, status=status.HTTP_200_OK)

# class RfidScanDetail(generics.RetrieveUpdateDestroyAPIView):
#     queryset = RfidScan.objects.all()
#     serializer_class = RfidScanSerializer
#     authentication_classes: list = []      # ✅ open for your standalone HTML
#     permission_classes = [AllowAny]
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from django.utils.dateparse import parse_date
from django.db.models import Count
from datetime import datetime

from .models import RfidScan
from .serializers import RfidScanSerializer
from RSSDairy.sse import broadcaster



class RfidScanListCreate(generics.ListCreateAPIView):
    serializer_class = RfidScanSerializer
    queryset = RfidScan.objects.all().order_by("-updated_at")
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        uid = request.data.get("uid")
        if not uid:
            return Response({"error": "uid is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Parse date/time coming from Pi
        date_str = request.data.get("date")
        time_str = request.data.get("time")
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
        except Exception:
            return Response({"error": "Invalid date/time format"}, status=status.HTTP_400_BAD_REQUEST)

        # Decide direction (IN / OUT) based on last scan for this uid
        last_scan = (
            RfidScan.objects.filter(uid=uid)
            .order_by("-updated_at")
            .first()
        )

        if last_scan is None or last_scan.date != date_obj:
            # First scan ever OR first scan of the day → assume cow was inside, now going OUT
            direction = "OUT"
        else:
            # Alternate: OUT → IN → OUT → IN ...
            direction = "IN" if last_scan.direction == "OUT" else "OUT"

        # Validate other fields with serializer
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Keep your name → block mapping
        name_val = serializer.validated_data.get("name") or request.data.get("name")
        block_override = None
        if name_val:
            try:
                name_clean = str(name_val).strip().lower()
            except Exception:
                name_clean = ""
            if name_clean == "desh":
                block_override = "A"
            elif name_clean == "bholu":
                block_override = "B"

        save_kwargs = {
            "uid": uid,
            "date": date_obj,
            "time": time_obj,
            "direction": direction,
        }
        if block_override is not None:
            save_kwargs["block"] = block_override

        # Always create a NEW row (no instance=instance)
        obj = serializer.save(**save_kwargs)

        out = RfidScanSerializer(obj).data
        try:
            broadcaster.publish(out)
        except Exception:
            pass

        # Use 201 for "created"
        return Response(out, status=status.HTTP_201_CREATED)


class RfidScanDetail(generics.RetrieveUpdateDestroyAPIView):
    queryset = RfidScan.objects.all()
    serializer_class = RfidScanSerializer
    authentication_classes: list = []
    permission_classes = [AllowAny]

class MissingCowsView(APIView):
    """
    GET /api/missing-cows/?date=2025-12-05  (date optional, defaults to today)

    Returns all uid/name where number of scans that day is odd.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        date_str = request.query_params.get("date")
        if date_str:
            date_obj = parse_date(date_str)
        else:
            date_obj = datetime.now().date()

        if not date_obj:
            return Response({"error": "Invalid date parameter"}, status=status.HTTP_400_BAD_REQUEST)

        qs = (
            RfidScan.objects.filter(date=date_obj)
            .values("uid", "name")
            .annotate(scan_count=Count("id"))
        )

        missing = [
            {
                "uid": row["uid"],
                "name": row["name"],
                "scan_count": row["scan_count"],
            }
            for row in qs
            if row["scan_count"] % 2 == 1
        ]

        return Response(
            {
                "date": date_obj,
                "missing_count": len(missing),
                "missing_cows": missing,
            }
        )



class AttendanceSummaryView(APIView):
    """
    GET /api/attendance-summary/?date=YYYY-MM-DD   (date optional; default today)

    Returns, for each cow that has any scan that day:
      - total_scans
      - out_scans
      - in_scans
      - outside (True/False)
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        date_str = request.query_params.get("date")
        if date_str:
            date_obj = parse_date(date_str)
        else:
            date_obj = datetime.now().date()

        if not date_obj:
            return Response({"error": "Invalid date parameter"}, status=400)

        # Aggregate per uid/name
        base_qs = RfidScan.objects.filter(date=date_obj)

        agg = (
            base_qs.values("uid", "name")
            .annotate(
                total_scans=Count("id"),
                out_scans=Count("id", filter=Q(direction="OUT")),
                in_scans=Count("id", filter=Q(direction="IN")),
            )
            .order_by("name", "uid")
        )

        results = []
        for row in agg:
            # A simple rule: if OUT scans > IN scans → cow is still outside
            outside = row["out_scans"] > row["in_scans"]
            results.append(
                {
                    "uid": row["uid"],
                    "name": row["name"],
                    "total_scans": row["total_scans"],
                    "out_scans": row["out_scans"],
                    "in_scans": row["in_scans"],
                    "outside": outside,
                }
            )

        return Response(
            {
                "date": date_obj,
                "count": len(results),
                "attendance": results,
            }
        )

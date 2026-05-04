"use client";

import { MapContainer, TileLayer, CircleMarker, Popup } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect } from "react";

const CENTER: [number, number] = [12.9716, 77.5946];

const COORDS: Record<string, [number, number]> = {
  Jayanagar: [12.925, 77.5938],
  Indiranagar: [12.9784, 77.6408],
  Whitefield: [12.9698, 77.75],
  Koramangala: [12.9352, 77.6245],
  Hebbal: [13.0358, 77.597],
  "Electronic City": [12.8456, 77.6603],
  Yelahanka: [13.1007, 77.5963],
  Marathahalli: [12.9591, 77.6974],
  Rajajinagar: [12.9915, 77.5543],
  "BTM Layout": [12.9166, 77.61],
};

function riskColor(level: string) {
  switch (level) {
    case "CRITICAL":
      return "#FF2D55";
    case "HIGH":
      return "#FF6B35";
    case "MEDIUM":
      return "#FFC857";
    default:
      return "#00E676";
  }
}

function FixIcons() {
  useEffect(() => {
    delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png",
      iconUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png",
      shadowUrl: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png",
    });
  }, []);
  return null;
}

export type Zone = {
  locality: string;
  peak_hour: number;
  max_risk_level: string;
  avg_predicted_kwh: number;
  flagged_meter_count: number;
};

export function ZoneMap({ zones }: { zones: Zone[] }) {
  return (
    <div className="relative h-[420px] w-full overflow-hidden rounded-xl border border-slate-800">
      <MapContainer center={CENTER} zoom={11} className="h-full w-full" scrollWheelZoom>
        <FixIcons />
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {zones.map((z) => {
          const pos = COORDS[z.locality] ?? CENTER;
          const color = riskColor(z.max_risk_level);
          return (
            <CircleMarker
              key={z.locality}
              center={pos}
              radius={12 + Math.min(16, z.flagged_meter_count)}
              pathOptions={{ color, fillColor: color, fillOpacity: 0.55, weight: 2 }}
            >
              <Popup>
                <div className="text-slate-900">
                  <div className="font-semibold">{z.locality}</div>
                  <div>Risk: {z.max_risk_level}</div>
                  <div>Peak hour: {z.peak_hour}:00</div>
                  <div>Flagged meters: {z.flagged_meter_count}</div>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
      <div className="pointer-events-none absolute bottom-3 right-3 rounded-lg border border-slate-700 bg-black/60 px-3 py-2 text-[11px] text-slate-200 backdrop-blur">
        <div className="mb-1 font-semibold text-slate-300">Risk legend</div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-6 rounded" style={{ background: "#00E676" }} /> LOW
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-6 rounded" style={{ background: "#FFC857" }} /> MEDIUM
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-6 rounded" style={{ background: "#FF6B35" }} /> HIGH
        </div>
        <div className="flex items-center gap-2">
          <span className="h-2 w-6 rounded" style={{ background: "#FF2D55" }} /> CRITICAL
        </div>
      </div>
    </div>
  );
}

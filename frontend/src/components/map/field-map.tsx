"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import mapboxgl from "mapbox-gl";
import { MAPBOX_TOKEN } from "@/lib/utils";
import type { Field } from "@/types/api";

mapboxgl.accessToken = MAPBOX_TOKEN;

interface FieldMapProps {
  fields: Field[];
  selectedFieldId?: string | null;
  onFieldClick?: (field: Field) => void;
  className?: string;
  interactive?: boolean;
}

export function FieldMap({
  fields,
  selectedFieldId,
  onFieldClick,
  className = "h-[500px]",
  interactive = true,
}: FieldMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new mapboxgl.Map({
      container: mapContainer.current,
      style: "mapbox://styles/mapbox/satellite-streets-v12",
      center: [-96, 41],
      zoom: 5,
      interactive,
    });

    map.addControl(new mapboxgl.NavigationControl(), "top-right");

    map.on("load", () => {
      mapRef.current = map;
      setLoaded(true);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [interactive]);

  // Update fields layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loaded) return;

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: fields
        .filter((f) => f.geometry)
        .map((f) => ({
          type: "Feature" as const,
          id: f.id,
          properties: {
            id: f.id,
            name: f.name,
            area_acres: f.area_acres,
            selected: f.id === selectedFieldId,
          },
          geometry: f.geometry!,
        })),
    };

    if (map.getSource("fields")) {
      (map.getSource("fields") as mapboxgl.GeoJSONSource).setData(geojson);
    } else {
      map.addSource("fields", { type: "geojson", data: geojson });

      map.addLayer({
        id: "fields-fill",
        type: "fill",
        source: "fields",
        paint: {
          "fill-color": [
            "case",
            ["get", "selected"],
            "#22c55e",
            "#3b82f6",
          ],
          "fill-opacity": 0.25,
        },
      });

      map.addLayer({
        id: "fields-outline",
        type: "line",
        source: "fields",
        paint: {
          "line-color": [
            "case",
            ["get", "selected"],
            "#16a34a",
            "#2563eb",
          ],
          "line-width": 2,
        },
      });

      map.addLayer({
        id: "fields-label",
        type: "symbol",
        source: "fields",
        layout: {
          "text-field": ["get", "name"],
          "text-size": 12,
          "text-anchor": "center",
        },
        paint: {
          "text-color": "#ffffff",
          "text-halo-color": "#000000",
          "text-halo-width": 1,
        },
      });

      if (onFieldClick) {
        map.on("click", "fields-fill", (e) => {
          const feature = e.features?.[0];
          if (feature?.properties?.id) {
            const field = fields.find(
              (f) => f.id === feature.properties!.id,
            );
            if (field) onFieldClick(field);
          }
        });

        map.on("mouseenter", "fields-fill", () => {
          map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", "fields-fill", () => {
          map.getCanvas().style.cursor = "";
        });
      }
    }

    // Fit bounds
    if (geojson.features.length > 0) {
      const bounds = new mapboxgl.LngLatBounds();
      geojson.features.forEach((f) => {
        const coords =
          f.geometry.type === "MultiPolygon"
            ? f.geometry.coordinates.flat(2)
            : f.geometry.type === "Polygon"
              ? f.geometry.coordinates.flat()
              : [];
        coords.forEach((c) => bounds.extend(c as [number, number]));
      });
      map.fitBounds(bounds, { padding: 60, maxZoom: 15 });
    }
  }, [fields, selectedFieldId, loaded, onFieldClick]);

  return (
    <div ref={mapContainer} className={`rounded-xl overflow-hidden ${className}`} />
  );
}

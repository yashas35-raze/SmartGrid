def detect_grid_anomaly(load, generation, prev_load, grid_status, defenses):

    # ---------------------------------
    # Step 1: Feature Extraction
    # ---------------------------------
    load_change = load - prev_load
    load_ratio = load / generation if generation > 0 else 0
    # Real-time instability detection (based on behavior)
    instability = abs(load_change) > 40

    # ---------------------------------
    # Step 2: Primary Threat Detection
    # ---------------------------------
    risk = 10
    detection = "Normal Operation"
    recommendation = "System operating normally"

    if load_change > 50 and instability:
        risk = 85
        detection = "Coordinated Grid Attack"
        recommendation = "Activate emergency defenses immediately"

    elif load_ratio > 1.0:
        risk = 75
        detection = "Grid Overload"
        recommendation = "Reduce load or increase generation"

    elif load_change > 80:
        risk = 65
        detection = "Load Injection Attack"
        recommendation = "Investigate abnormal load spike"

    elif instability:
        risk = 55
        detection = "Grid Instability"
        recommendation = "Stabilize generation and monitor grid"

    elif 20 < load_change <= 50:
        risk = 40
        detection = "Suspicious Load Manipulation"
        recommendation = "Monitor smart meter integrity"

    # ---------------------------------
    # Step 3: Contextual Risk Modifiers
    # ---------------------------------

    # Defense weakness (small penalties)
    if not defenses.get("authGateway", False):
        risk += 5

    if not defenses.get("firewall", False):
        risk += 5

    if not defenses.get("anomalyDetection", False):
        risk += 3

    # Rapid load spike (secondary signal)
    if load_change > 70:
        risk += 5

    # Near capacity warning
    if 0.85 < load_ratio <= 1.0:
        risk += 5

    # Stable condition bonus (reduce noise)
    if load_change < 10 and not instability:
        risk -= 5

    # ---------------------------------
    # Step 4: Defense Bypass Detection (Refined)
    # ---------------------------------
    if risk >= 70 and (
        not defenses.get("authGateway", False) or
        not defenses.get("firewall", False)
    ):
        detection = "Defense Bypass Attempt"
        recommendation = "Enable all critical defenses immediately"
        risk += 5  # small bump, not explosion

    # ---------------------------------
    # Step 5: Risk Normalization
    # ---------------------------------
    risk = max(0, min(risk, 100))

    return risk, detection, recommendation
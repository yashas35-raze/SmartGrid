using UnityEngine;
using Firebase.Database;
using System;
using System.Linq;
using System.Collections.Generic;
using Unity.VisualScripting;
using System.ComponentModel;

public class FirebaseGridManager : MonoBehaviour
{
    private DatabaseReference gridRef;
    private DatabaseReference commandRef;

    public static string CurrentPowerState = "OFF";
    public static string CurrentAttackState = "NONE";

    // Power configuration
    public float powerPerLight = 3f;
    public float reserveMargin = 50f;
    public float maxGeneration = 300f;

    [Header("Runtime Monitoring")]
    public float currentGeneration = 0f;
    public float smoothedLoad = 0f;

    // Blackout timer system
    private bool blackoutActive = false;
    private float blackoutTimer = 0f;
    public float blackoutDuration = 10f;
    private float remainingBlackoutTime = 0f;

    // Defense Systems
    private bool authGatewayEnabled = false;
    private bool firewallEnabled = false;
    private bool anomalyDetectionEnabled = false;

    //Tampered meter values
    private Dictionary<string, float> tamperedMeters = new Dictionary<string, float>();

    private HashSet<string> blackoutMeters = new HashSet<string>();

    // ----------------------------
    // Grid Overload Attack System
    // ----------------------------
    private bool overloadAttackActive = false;
    private float overloadTimer = 0f;
    public float overloadDuration = 5f;

    void Start()
    {
        gridRef = FirebaseDatabase.DefaultInstance.GetReference("grid");
        commandRef = FirebaseDatabase.DefaultInstance.GetReference("command");

        // Listen to grid changes
        gridRef.Child("power").ValueChanged += OnPowerChanged;
        gridRef.Child("attack").ValueChanged += OnAttackChanged;
        gridRef.Child("defenses").Child("authGateway").ValueChanged += OnAuthGatewayChanged;
        gridRef.Child("defenses").Child("firewall").ValueChanged += OnFirewallChanged;
        gridRef.Child("defenses").Child("anomalyDetection").ValueChanged += OnAnomalyDetectionChanged;

        // 🔥 NEW: Listen to command node
        commandRef.ValueChanged += OnCommandReceived;

        InitializeDefaultState();

        ForceAllLightsOff();

        InvokeRepeating(nameof(UpdateGridStatus), 0.2f, 0.2f);
    }

    // ----------------------------
    // GRID STATE LISTENERS
    // ----------------------------

    private void OnPowerChanged(object sender, ValueChangedEventArgs args)
    {
        if (args.Snapshot?.Value == null) return;
        CurrentPowerState = args.Snapshot.Value.ToString();
        Debug.Log("Power Updated From Firebase: " + CurrentPowerState);
    }

    private void OnAttackChanged(object sender, ValueChangedEventArgs args)
    {
        if (args.Snapshot?.Value == null) return;
        CurrentAttackState = args.Snapshot.Value.ToString();
        Debug.Log("Attack Updated From Firebase: " + CurrentAttackState);
    }

    private void OnAuthGatewayChanged(object sender, ValueChangedEventArgs args)

    {
        if (args.Snapshot?.Value == null)
        {
            authGatewayEnabled = false;
            return;
        }

        bool.TryParse(args.Snapshot.Value.ToString(), out authGatewayEnabled);

        Debug.Log("Auth Gateway Updated: " + authGatewayEnabled);
    }

    private void OnFirewallChanged(object sender, ValueChangedEventArgs args)
    {
        if (args.Snapshot?.Value == null)
        {
            firewallEnabled = false;
            return;
        }
        bool.TryParse(args.Snapshot.Value.ToString(), out firewallEnabled);

        Debug.Log("Firewall Updated: " + firewallEnabled);
    }

    private void OnAnomalyDetectionChanged(object sender, ValueChangedEventArgs args)
    {
        if (args.Snapshot?.Value == null)
        {
            anomalyDetectionEnabled = false;
            return;
        }
        bool.TryParse(args.Snapshot.Value.ToString(), out anomalyDetectionEnabled);

        Debug.Log("Anomaly Detection Updated: " + anomalyDetectionEnabled);
    }

    // ----------------------------
    // 🔥 COMMAND LISTENER
    // ----------------------------

    private void OnCommandReceived(object sender, ValueChangedEventArgs args)
    {
        if (args.Snapshot?.Value == null) return;

        string command = args.Snapshot.Child("command").Value?.ToString();
        string targetID = args.Snapshot.Child("targetID").Value?.ToString();
        float value = 0f;

        float.TryParse(args.Snapshot.Child("value").Value?.ToString(), out value);

        // Auth Gateway Check
        if (authGatewayEnabled)
        {
            if (command == "BLACKOUT" || command == "OVERLOAD")
            {
                Debug.Log("Auth Gateway Blocked Command: " + command);

                // Clear command so it doesn't loop
                commandRef.Child("command").SetValueAsync("NONE");

                return;
            }
        }

        Debug.Log("Command Received: " + command);

        // ---------------------------
        // Data Injection Attack
        // ---------------------------

        if (command == "TAMPER_METER")
        {
            Debug.Log("Meter tampering attack on: " + targetID + " value: " + value);

            tamperedMeters[targetID] = value;

            commandRef.Child("command").SetValueAsync("NONE");
        }

        // ---------------------------
        // Reset Tampered Meters
        // ---------------------------

        if (command == "RESET_TAMPERS")
        {
            Debug.Log("Resetting all tampered meter values");

            tamperedMeters.Clear();

            commandRef.Child("command").SetValueAsync("NONE");
        }


        // ----------------------------
        // Grid Overload Attack
        // ----------------------------

        if (command == "LOAD_SPIKE")
        {
            Debug.Log("Grid Overload Attack Triggered");

            gridRef.Child("attack").SetValueAsync("LOAD_SPIKE");

            overloadAttackActive = true;
            overloadTimer = overloadDuration;

            commandRef.Child("command").SetValueAsync("NONE");
        }

        // ---------------------------
        // Grid Instability Attack
        // ---------------------------

        if (command == "INDUCE_INSTABILITY")
        {
            Debug.Log("Grid Instability Attack Triggered");

            gridRef.Child("attack").SetValueAsync("INSTABILITY");

            // Increase load fluctuations
            smoothedLoad += UnityEngine.Random.Range(20f, 60f);

            // Trigger flickering effect
            StartCoroutine(FlickerLights());

            commandRef.Child("command").SetValueAsync("NONE");
        }

        if (command == "RESET_TRIP")
        {
            ResetTrip_Selected();

            // Clear command so it doesn't loop
            commandRef.Child("command").SetValueAsync("NONE");
        }

        // ------------------------
        // GRID POWER CONTROL
        // ------------------------

        if (command == "GRID_ON")
        {
            Debug.Log("Grid turned ON by operator");

            gridRef.Child("power").SetValueAsync("ON");
            gridRef.Child("shutdownReason").SetValueAsync("NONE");

            // All lights off when turning on grid
            SetAllLights("OFF");

            commandRef.Child("command").SetValueAsync("NONE");
        }

        if (command == "GRID_OFF")
        {
            Debug.Log("Grid turned OFF by operator");

            gridRef.Child("power").SetValueAsync("OFF");
            gridRef.Child("shutdownReason").SetValueAsync("MANUAL");

            //Set lights off
            SetAllLights("OFF");

            commandRef.Child("command").SetValueAsync("NONE");
        }


        if (command == "SET_LIGHTS")
        {
            if (CurrentPowerState != "ON")
            {
                Debug.Log("Lights cannot turn ON - Grid is OFF");

                commandRef.Child("command").SetValueAsync("NONE");
                return;
            }
            string state = value == 1.0f ? "ON" : "OFF";

            SetAllLights(state);
            Debug.Log("All lights set to:" + state);
            commandRef.Child("command").SetValueAsync("NONE");
        }

        if (command == "BLACKOUT")
        {
            // 🔥 FIREWALL CHECK
            if (firewallEnabled)
            {
                Debug.Log("Firewall Blocked BLACKOUT Attack");

                commandRef.Child("command").SetValueAsync("NONE");
                return;
            }

            // Targeted blackout if meter ID provided
            if (!string.IsNullOrEmpty(targetID))
            {
                Debug.Log("Targeted blackout on: " + targetID);

                blackoutMeters.Add(targetID);

                gridRef.Parent
                    .Child("devices")
                    .Child(targetID)
                    .Child("blackout")
                    .SetValueAsync(true);

                commandRef.Child("command").SetValueAsync("NONE");
                return;
            }

            if (!blackoutActive)
            {
                Debug.Log("Blackout attack started");

                blackoutActive = true;
                blackoutTimer = blackoutDuration;
                remainingBlackoutTime = blackoutDuration;
                gridRef.Child("attack").SetValueAsync("BLACKOUT");

                commandRef.Child("command").SetValueAsync("NONE");
            }
        }

        // ---------------------------
        // Reset Targeted Blackout
        // ---------------------------

        if (command == "RESET_TARGETED_BLACKOUT")
        {
            Debug.Log("Resetting targeted blackout on: " + targetID);
            if (!string.IsNullOrEmpty(targetID))
            {
                blackoutMeters.Remove(targetID);

                var meterRef = FirebaseDatabase.DefaultInstance
                    .GetReference($"devices/{targetID}");

                // Remove blackout flag
                meterRef.Child("blackout").SetValueAsync(false);

                // Restore consumption
                meterRef.Child("power_consumption").SetValueAsync(12);

                // Restore all lights
                meterRef.Child("lights").GetValueAsync().ContinueWith(task =>
                {
                    if (task.Result != null)
                    {
                        foreach (var light in task.Result.Children)
                        {
                            meterRef.Child("lights")
                                .Child(light.Key)
                                .Child("state")
                                .SetValueAsync("ON");
                        }
                    }
                });
            }

            commandRef.Child("command").SetValueAsync("NONE");
        }

        if (command == "SET_DEFENSE")
        {
            Debug.Log("Defense Toggle Received: " + targetID);

            // Authentication button pressed
            if (targetID == "authentication")
            {
                authGatewayEnabled = !authGatewayEnabled;
                gridRef.Child("defenses").Child("authGateway").SetValueAsync(authGatewayEnabled);
            }

            // Firewall button pressed
            if (targetID == "firewall")
            {
                firewallEnabled = !firewallEnabled;
                gridRef.Child("defenses").Child("firewall").SetValueAsync(firewallEnabled);
            }

            // Anomaly button pressed
            if (targetID == "anomaly")
            {
                anomalyDetectionEnabled = !anomalyDetectionEnabled;
                gridRef.Child("defenses").Child("anomalyDetection").SetValueAsync(anomalyDetectionEnabled);
            }

            commandRef.Child("command").SetValueAsync("NONE");
        }
    }

    // ----------------------------
    // 🔥 SET ALL LIGHTS
    // ----------------------------

    void SetAllLights(string state)
    {
        var devicesRef = FirebaseDatabase.DefaultInstance.GetReference("devices");

        devicesRef.GetValueAsync().ContinueWith(task =>
        {
            if (task.Result != null)
            {
                foreach (var meter in task.Result.Children)
                {
                    var lightsRef = devicesRef
                        .Child(meter.Key)
                        .Child("lights");

                    lightsRef.GetValueAsync().ContinueWith(lightTask =>
                    {
                        if (lightTask.Result != null)
                        {
                            foreach (var light in lightTask.Result.Children)
                            {
                                lightsRef
                                    .Child(light.Key)
                                    .Child("state")
                                    .SetValueAsync(state);
                            }
                        }
                    });
                }
            }
        });
    }

    void ForceAllLightsOff()
    {
        var lights = FindObjectsByType<LightController>(FindObjectsSortMode.None);

        foreach (var lc in lights)
        {
            Light l = lc.GetComponent<Light>();

            if (l != null)
                l.enabled = false;
        }
    }


    // -----------------------------------
    // Initializing Default Values
    // -----------------------------------

    void InitializeDefaultState()
    {
        Debug.Log("Initializing Grid to Default OFF State");

        long epoch = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

        // Reset grid core values
        gridRef.Child("power").SetValueAsync("OFF");
        gridRef.Child("attack").SetValueAsync("NONE");
        gridRef.Child("totalLoad").SetValueAsync(0f);
        gridRef.Child("totalGeneration").SetValueAsync(0f);
        gridRef.Child("maxGeneration").SetValueAsync(maxGeneration);
        gridRef.Child("gridStatus").SetValueAsync("OFFLINE");
        gridRef.Child("remainingBlackoutTime").SetValueAsync(0f);
        gridRef.Child("timestamp_epoch").SetValueAsync(epoch);

        // Reset all meter power consumption
        var devicesRef = gridRef.Parent.Child("devices");

        devicesRef.GetValueAsync().ContinueWith(task =>
        {
            if (task.Result != null)
            {
                foreach (var meter in task.Result.Children)
                {
                    devicesRef.Child(meter.Key)
                        .Child("power_consumption")
                        .SetValueAsync(0f);

                    devicesRef.Child(meter.Key)
                        .Child("blackout")
                        .SetValueAsync(false);
                }
            }
        });
    }

    // ----------------------------
    // GRID STATUS UPDATE
    // ----------------------------

    void UpdateGridStatus()
    {
        if (gridRef == null) return;



        //Blackout timer handling
        if (blackoutActive)
        {
            blackoutTimer -= 0.2f;
            remainingBlackoutTime = blackoutTimer;
            gridRef.Child("remainingBlackoutTime").SetValueAsync(Mathf.Max(0, remainingBlackoutTime));
            Debug.Log("Blackout time left: " + remainingBlackoutTime.ToString("F1"));

            if (blackoutTimer <= 0f)
            {
                Debug.Log("Blackout ended automatically");

                blackoutActive = false;
                blackoutTimer = 0f;

                gridRef.Child("attack").SetValueAsync("NONE");
            }
        }

        long epoch = DateTimeOffset.UtcNow.ToUnixTimeSeconds();

        var lights = FindObjectsByType<LightController>(FindObjectsSortMode.None);

        Dictionary<string, int> meterLightCount = new Dictionary<string, int>();

        foreach (var lc in lights)
        {
            Light unityLight = lc.GetComponent<Light>();

            if (unityLight == null) continue;

            // 🔥 Turn off lights for blackout meters
            if (blackoutMeters.Contains(lc.meterId))
            {
                unityLight.enabled = false;
                continue;
            }

            // Normal load counting
            if (unityLight.enabled)
            {
                if (!meterLightCount.ContainsKey(lc.meterId))
                    meterLightCount[lc.meterId] = 0;

                meterLightCount[lc.meterId]++;
            }
        }

        float totalLoad = 0f;
        float totalGeneration = 0f;
        string status = "STABLE";

        if (CurrentPowerState == "OFF")
        {
            totalLoad = 0f;
            smoothedLoad = 0f;
            totalGeneration = 0f;
            currentGeneration = 0f;
            status = "OFFLINE";
        }

        else if (CurrentPowerState == "TRIPPED")
        {
            totalLoad = 0f;
            smoothedLoad = 0f;
            totalGeneration = 0f;
            currentGeneration = 0f;
            status = "PROTECTIVE_TRIP";
        }

        else if (CurrentPowerState == "BLACKOUT")
        {
            totalLoad = 0f;
            smoothedLoad = 0f;
            totalGeneration = 0f;
            status = "BLACKOUT";
        }
        else
        {
            // If lights are OFF globally, load must be zero
            if (meterLightCount.Count == 0)
            {
                totalLoad = 0f;
            }
            else
            {
                foreach (var entry in meterLightCount)
                {
                    float meterLoad;

                    if (tamperedMeters.ContainsKey(entry.Key))
                    {
                        meterLoad = tamperedMeters[entry.Key]; // attacker injected value
                    }
                    else
                    {
                        meterLoad = entry.Value * powerPerLight; // normal calculated load
                    }

                    gridRef.Parent.Child("devices")
                        .Child(entry.Key)
                        .Child("power_consumption")
                        .SetValueAsync(meterLoad);

                    totalLoad += meterLoad;
                }
            }

            // Apply overload attack after real load calculation

            if (overloadAttackActive)
            {
                overloadTimer -= 0.2f;

                totalLoad += 200f;

                if (overloadTimer <= 0f)
                {
                    overloadAttackActive = false;
                    Debug.Log("Overload attack ended");
                }
            }

            // Generation depends only on grid state
            if (CurrentPowerState == "ON")
            {
                float targetGeneration = Mathf.Min(maxGeneration, totalLoad + reserveMargin);
                currentGeneration = Mathf.Lerp(currentGeneration, targetGeneration, 0.05f);
                totalGeneration = currentGeneration;
            }
            else
            {
                totalGeneration = 0f;
                currentGeneration = 0f;
            }

            if (totalLoad > maxGeneration)
            {
                if (anomalyDetectionEnabled)
                {
                    Debug.Log("Anomaly detected and contained by detection system");
                    status = "PROTECTED";
                    return;
                }
                Debug.Log("Grid Overload! Protective Trip Activated...");

                status = "PROTECTIVE_TRIP";
                CurrentPowerState = "TRIPPED";

                SetAllLights("OFF");
                currentGeneration = 0f;

                gridRef.Child("shutdownReason").SetValueAsync("PROTECTIVE_TRIP");
                blackoutActive = false;
            }

        }
        totalGeneration = currentGeneration;
        if (overloadAttackActive)
        {
            smoothedLoad = totalLoad;   // show spike immediately
        }
        else
        {
            smoothedLoad = Mathf.Lerp(smoothedLoad, totalLoad, 0.05f);
        }
        // Force 0 when load becomes 0
        if (smoothedLoad < 1.15f)
        {
            smoothedLoad = 0f;
        }
        gridRef.Child("totalLoad").SetValueAsync(smoothedLoad);
        gridRef.Child("totalGeneration").SetValueAsync(totalGeneration);
        gridRef.Child("gridStatus").SetValueAsync(status);
        gridRef.Child("timestamp_epoch").SetValueAsync(epoch);
        gridRef.Child("maxGeneration").SetValueAsync(maxGeneration);
    }

    //Unity buttons
    public void PowerOn_Selected()
    {
        gridRef.Child("power").SetValueAsync("ON");
        gridRef.Child("attack").SetValueAsync("NONE");
        gridRef.Child("shutdownReason").SetValueAsync("NONE");
    }

    public void PowerOff_Selected()
    {
        gridRef.Child("power").SetValueAsync("OFF");
        gridRef.Child("attack").SetValueAsync("NONE");
        gridRef.Child("shutdownReason").SetValueAsync("MANUAL");
    }

    public void Blackout_Selected()
    {
        if (!blackoutActive)
        {
            blackoutActive = true;
            blackoutTimer = blackoutDuration;

            gridRef.Child("attack").SetValueAsync("BLACKOUT");
        }
    }
    public void ClearBlackout_Selected()
    {
        Debug.Log("Operator manually cleared blackout");

        blackoutActive = false;
        blackoutTimer = 0f;

        gridRef.Child("attack").SetValueAsync("NONE");
    }

    public void ResetTrip_Selected()
    {
        Debug.Log("Operator Reset Protective Trip");

        CurrentPowerState = "OFF";
        currentGeneration = 0f;

        // Reset attack states
        overloadAttackActive = false;
        overloadTimer = 0f;

        gridRef.Child("power").SetValueAsync("OFF");
        gridRef.Child("attack").SetValueAsync("NONE");
        gridRef.Child("shutdownReason").SetValueAsync("NONE");
        gridRef.Child("gridStatus").SetValueAsync("STABLE");
        SetAllLights("OFF");
    }

    // Light Flickering
    System.Collections.IEnumerator FlickerLights()
    {
        var lights = FindObjectsByType<LightController>(FindObjectsSortMode.None);

        List<Light> gridLights = new List<Light>();

        foreach (var lc in lights)
        {
            Light l = lc.GetComponent<Light>();

            if (l != null)
                gridLights.Add(l);
        }

        // store original intensities
        Dictionary<Light, float> original = new Dictionary<Light, float>();

        foreach (var l in gridLights)
            original[l] = l.intensity;

        for (int cycle = 0; cycle < 6; cycle++)
        {
            foreach (var l in gridLights)
            {
                float chance = UnityEngine.Random.value;

                if (chance < 0.25f)
                {
                    // simulate power drop
                    l.intensity = 0f;
                }
                else
                {
                    l.intensity = original[l] * UnityEngine.Random.Range(0.2f, 1.3f);
                }
            }

            yield return new WaitForSeconds(1.2f);
        }

        // restore normal lighting
        foreach (var l in gridLights)
            l.intensity = original[l];
    }



    // ----------------------------
    // CLEANUP
    // ----------------------------

    private void OnDestroy()
    {
        if (gridRef != null)
        {
            gridRef.Child("power").ValueChanged -= OnPowerChanged;
            gridRef.Child("attack").ValueChanged -= OnAttackChanged;

            gridRef.Child("defenses").Child("authGateway").ValueChanged -= OnAuthGatewayChanged;
            gridRef.Child("defenses").Child("firewall").ValueChanged -= OnFirewallChanged;
            gridRef.Child("defenses").Child("anomalyDetection").ValueChanged -= OnAnomalyDetectionChanged;
        }

        if (commandRef != null)
        {
            commandRef.ValueChanged -= OnCommandReceived;
        }

        CancelInvoke(nameof(UpdateGridStatus));
    }
}

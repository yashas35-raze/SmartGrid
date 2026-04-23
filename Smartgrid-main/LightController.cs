using UnityEngine;
using Firebase.Database;

public class LightController : MonoBehaviour
{
    [Header("Identification")]
    public string meterId;
    public string lightId;

    private DatabaseReference lightRef;
    private DatabaseReference meterRef;
    private Light unityLight;

    private string localState = "OFF";
    private bool isInitialized = false;

    private bool meterBlackout = false;

    void Start()
    {
        unityLight = GetComponent<Light>();

        if (unityLight == null)
        {
            Debug.LogError($"Light component missing on {gameObject.name}");
            return;
        }

        if (string.IsNullOrEmpty(meterId))
        {
            Debug.LogError($"Meter ID not assigned on {gameObject.name}");
            return;
        }

        if (string.IsNullOrEmpty(lightId))
            lightId = gameObject.name;

        meterRef = FirebaseDatabase.DefaultInstance
            .GetReference($"devices/{meterId}");

        lightRef = FirebaseDatabase.DefaultInstance
            .GetReference($"devices/{meterId}/lights/{lightId}");

        InitializeMeterStructure();
        InitializeLight();

        // Listen for light state changes
        lightRef.Child("state").ValueChanged += OnLightChanged;

        meterRef.Child("blackout").ValueChanged += OnMeterBlackoutChanged;
    }

    void Update()
    {
        ApplyFinalState();
    }

    void InitializeMeterStructure()
    {
        if (isInitialized) return;

        // Create base meter structure if not exists
        meterRef.Child("blackout").GetValueAsync().ContinueWith(task =>
        {
            if (task.IsCompleted && task.Result != null && !task.Result.Exists)
            {
                meterRef.Child("blackout").SetValueAsync(false);
            }
        });

        meterRef.Child("power_state").GetValueAsync().ContinueWith(task =>
        {
            if (task.IsCompleted && task.Result != null && !task.Result.Exists)
            {
                meterRef.Child("power_state").SetValueAsync("ON");
            }
        });

        meterRef.Child("power_consumption").GetValueAsync().ContinueWith(task =>
        {
            if (task.IsCompleted && task.Result != null && !task.Result.Exists)
            {
                meterRef.Child("power_consumption").SetValueAsync(0);
            }
        });

        isInitialized = true;
    }

    void InitializeLight()
    {
        // Auto register light if not exists
        lightRef.Child("state").GetValueAsync().ContinueWith(task =>
        {
            if (task.IsCompleted && task.Result != null && !task.Result.Exists)
            {
                lightRef.Child("state").SetValueAsync("OFF");
            }
        });
    }

    void OnLightChanged(object sender, ValueChangedEventArgs e)
    {
        if (e.Snapshot?.Value == null) return;

        localState = e.Snapshot.Value.ToString();
    }

    void OnMeterBlackoutChanged(object sender, ValueChangedEventArgs e)
    {
        if (e.Snapshot?.Value == null) return;

        bool.TryParse(e.Snapshot.Value.ToString(), out meterBlackout);
    }

    void ApplyFinalState()
    {
        if (unityLight == null) return;

        // GRID POWER OFF
        if (FirebaseGridManager.CurrentPowerState != "ON")
        {
            unityLight.enabled = false;
            return;
        }

        // GLOBAL BLACKOUT
        if (FirebaseGridManager.CurrentAttackState == "BLACKOUT")
        {
            unityLight.enabled = false;
            return;
        }

        // TARGETED BLACKOUT
        if (meterBlackout)
        {
            unityLight.enabled = false;
            return;
        }

        // NORMAL STATE
        unityLight.enabled = (localState == "ON");
    }

    private void OnDestroy()
    {
        if (lightRef != null)
        {
            lightRef.Child("state").ValueChanged -= OnLightChanged;
        }
    }
}


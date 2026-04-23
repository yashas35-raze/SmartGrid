using UnityEngine;
using Firebase.Database;
using System.Linq;

public class MeterController : MonoBehaviour
{
    public string meterId;
    public int powerPerLight = 10;

    private DatabaseReference meterRef;
    private bool meterOn = false;
    private bool firebaseReady = false;

    void Start()
    {
        meterRef = FirebaseDatabase.DefaultInstance
            .GetReference($"devices/{meterId}");

        if (meterRef != null)
        {
            firebaseReady = true;

            // Auto register
            meterRef.Child("power_state").SetValueAsync("OFF");
            meterRef.Child("blackout").SetValueAsync(false);
            meterRef.Child("power_consumption").SetValueAsync(0);

            meterRef.ValueChanged += OnMeterChanged;
        }

        InvokeRepeating(nameof(UpdatePower), 1f, 2f);
    }

    void OnMeterChanged(object sender, ValueChangedEventArgs e)
    {
        if (!e.Snapshot.Exists) return;

        bool blackout = bool.Parse(e.Snapshot.Child("blackout").Value.ToString());
        string power = e.Snapshot.Child("power_state").Value.ToString();

        meterOn = power == "ON" && !blackout;
    }

    void UpdatePower()
    {
        // 🔑 HARD STOP — prevents NullReference forever
        if (!firebaseReady || meterRef == null)
            return;

        if (!meterOn)
        {
            meterRef.Child("power_consumption").SetValueAsync(0);
            return;
        }

        var lights = FindObjectsByType<LightController>(FindObjectsSortMode.None)
            .Where(l => l != null && l.meterId == meterId);

        int activeLights = 0;

        foreach (var l in lights)
        {
            Light unityLight = l.GetComponent<Light>();
            if (unityLight != null && unityLight.enabled)
                activeLights++;
        }

        int consumption = activeLights * powerPerLight;
        meterRef.Child("power_consumption").SetValueAsync(consumption);
    }
}

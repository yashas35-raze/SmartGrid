using UnityEngine;
using Firebase.Database;

public class GridPowerButton : MonoBehaviour
{
    private DatabaseReference db;

    void Start()
    {
        db = FirebaseDatabase.DefaultInstance.RootReference;
    }

    public void PowerON()
    {
        SetGridPower("ON");
        SetPowerState("ON");
    }

    public void PowerOFF()
    {
        SetGridPower("OFF");
        SetPowerState("OFF");
    }

    void SetGridPower(string state)
    {
        db.Child("grid").Child("power").SetValueAsync(state);

        // 🔑 propagate to meters
        db.Child("devices").GetValueAsync().ContinueWith(task =>
        {
            if (!task.IsCompleted) return;

            foreach (var meter in task.Result.Children)
            {
                meter.Reference.Child("power_state")
                    .SetValueAsync(state);
            }
        });
    }

    void SetPowerState(string state)
    {
        db.Child("devices").GetValueAsync().ContinueWith(task =>
        {
            if (!task.IsCompleted || task.Result == null) return;

            foreach (var meter in task.Result.Children)
            {
                meter.Reference.Child("lights").GetValueAsync().ContinueWith(lightTask =>
                {
                    if (!lightTask.IsCompleted || lightTask.Result == null) return;
                    foreach (var light in lightTask.Result.Children)
                    {
                        light.Reference.Child("state").SetValueAsync(state);
                    }
                });
            }
        });
    }
}
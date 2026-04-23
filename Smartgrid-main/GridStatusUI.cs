using UnityEngine;
using TMPro;
using Firebase.Database;

public class GridStatusUI : MonoBehaviour
{
    public TextMeshProUGUI statusText;

    private DatabaseReference gridRef;

    void Start()
    {
        gridRef = FirebaseDatabase.DefaultInstance.GetReference("grid/gridStatus");
        gridRef.ValueChanged += OnStatusChanged;
    }

    void OnStatusChanged(object sender, ValueChangedEventArgs args)
    {
        if (args.Snapshot?.Value == null) return;

        string status = args.Snapshot.Value.ToString();
        statusText.text = "GRID: " + status;

        switch (status)
        {
            case "STABLE":
                statusText.color = Color.green;
                break;

            case "OVERLOAD":
                statusText.color = Color.red;
                break;

            case "OFFLINE":
                statusText.color = Color.gray;
                break;

            case "BLACKOUT":
                statusText.color = Color.black;
                break;

            default:
                statusText.color = Color.white;
                break;
        }
    }

    void OnDestroy()
    {
        if (gridRef != null)
            gridRef.ValueChanged -= OnStatusChanged;
    }
}
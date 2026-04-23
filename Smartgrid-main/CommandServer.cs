using System;
using System.Collections;
using System.Collections.Generic;
using System.Net;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

// ======================================================================
// CommandServer.cs  (Unity 6000 LTS Safe Version)
// ======================================================================
// ✔ Fully compiler-safe for Unity 6000.2.x
// ✔ No yield inside try/catch (fixes CS1626)
// ✔ No manual JSON building (fixes raw string errors)
// ✔ Correct coroutine layout
// ✔ Status + Log upload fully functional
// ✔ Command polling included
// ======================================================================

public class CommandServer : MonoBehaviour
{
    [Header("Firebase Settings")]
    public string firebaseUrl = "https://trip-a155a-default-rtdb.asia-southeast1.firebasedatabase.app/";
    public float pushIntervalSeconds = 2.0f;
    public float commandPollIntervalSeconds = 1.0f;

    // Runtime State
    private Coroutine pushLoop;
    private Coroutine pollLoop;

    private List<MeterData> meters = new List<MeterData>();
    private float totalGeneration = 0;
    private string gridStatus = "WAITING";
    private bool authenticationActive = true;
    private bool replayActive = false;
    private bool anomalyActive = false;
    private string internalLog = "";

    private double lastProcessedCmdTime = 0;

    // ======================================================================
    // Data Classes
    // ======================================================================

    [Serializable]
    public class MeterData
    {
        public string id;
        public string location;
        public double consumption;
    }

    [Serializable]
    public class StatusMessage
    {
        public List<MeterData> meters;
        public double totalGeneration;
        public string gridStatus;
        public string log;
        public bool authenticationActive;
        public bool replayActive;
        public bool anomalyActive;
        public double timestamp_epoch;
        public string timestamp_iso;
    }

    [Serializable]
    public class LogMessage
    {
        public string log;
        public double timestamp_epoch;
        public string timestamp_iso;
    }

    [Serializable]
    public class CommandMessage
    {
        public string type;
        public double timestamp;
        public string payload;
    }

    // ======================================================================
    // Unity Lifecycle
    // ======================================================================

    void Start()
    {
        PopulateMeters();

        pushLoop = StartCoroutine(PushStatusLoop());
        pollLoop = StartCoroutine(PollForCommands());
    }

    void OnDestroy()
    {
        if (pushLoop != null) StopCoroutine(pushLoop);
        if (pollLoop != null) StopCoroutine(pollLoop);
    }

    // ======================================================================
    // Populate Sample Meters
    // ======================================================================

    void PopulateMeters()
    {
        meters.Clear();
        for (int i = 0; i < 10; i++)
        {
            meters.Add(new MeterData()
            {
                id = "Meter-" + i,
                location = (i % 2 == 0) ? "City" : "Town",
                consumption = 0
            });
        }

        totalGeneration = 1200;
        gridStatus = "STABLE";
    }

    // ======================================================================
    // Push Status Loop
    // ======================================================================

    IEnumerator PushStatusLoop()
    {
        while (true)
        {
            StatusMessage sm = new StatusMessage();
            try
            {
                sm.meters = new List<MeterData>(meters);
                sm.totalGeneration = totalGeneration;
                sm.gridStatus = gridStatus;
                sm.log = internalLog;
                sm.authenticationActive = authenticationActive;
                sm.replayActive = replayActive;
                sm.anomalyActive = anomalyActive;

                DateTime now = DateTime.UtcNow;
                sm.timestamp_epoch = Math.Round((now - new DateTime(1970, 1, 1)).TotalSeconds, 3);
                sm.timestamp_iso = now.ToString("o");
            }
            catch (Exception e)
            {
                Debug.LogWarning("[CommandServer] Status build error: " + e);
            }

            string json = JsonUtility.ToJson(sm);

            UnityWebRequest req = UnityWebRequest.Put(firebaseUrl + "status.json", json);
            req.SetRequestHeader("Content-Type", "application/json");

            yield return req.SendWebRequest();

            if (req.result != UnityWebRequest.Result.Success)
                Debug.LogWarning("[CommandServer] Status upload failed: " + req.error + " (" + req.responseCode + ")");
            else
                Debug.Log("[CommandServer] Status uploaded OK");

            yield return new WaitForSeconds(pushIntervalSeconds);
        }
    }

    // ======================================================================
    // Upload Log
    // ======================================================================

    public void AppendLog(string text)
    {
        internalLog = text;
        StartCoroutine(UploadLogCoroutine(text));
    }

    IEnumerator UploadLogCoroutine(string log)
    {
        LogMessage lm = new LogMessage();
        try
        {
            DateTime now = DateTime.UtcNow;
            lm.log = log;
            lm.timestamp_epoch = Math.Round((now - new DateTime(1970, 1, 1)).TotalSeconds, 3);
            lm.timestamp_iso = now.ToString("o");
        }
        catch (Exception e)
        {
            Debug.LogWarning("[CommandServer] Log build error: " + e);
        }

        string json = JsonUtility.ToJson(lm);

        UnityWebRequest req = UnityWebRequest.Put(firebaseUrl + "status_log.json", json);
        req.SetRequestHeader("Content-Type", "application/json");

        yield return req.SendWebRequest();

        if (req.result != UnityWebRequest.Result.Success)
            Debug.LogWarning("[CommandServer] Log upload failed: " + req.error + " (" + req.responseCode + ")");
        else
            Debug.Log("[CommandServer] Log uploaded OK");
    }

    // ======================================================================
    // Poll Commands
    // ======================================================================

    IEnumerator PollForCommands()
    {
        while (true)
        {
            UnityWebRequest req = UnityWebRequest.Get(firebaseUrl + "command.json");

            yield return req.SendWebRequest();

            if (req.result == UnityWebRequest.Result.Success)
            {
                string raw = req.downloadHandler.text;

                if (!string.IsNullOrEmpty(raw) && raw != "null")
                {
                    CommandMessage msg = null;
                    try
                    {
                        msg = JsonUtility.FromJson<CommandMessage>(raw);
                    }
                    catch (Exception e)
                    {
                        Debug.LogWarning("[CommandServer] Command parse error: " + e);
                    }

                    if (msg != null && msg.timestamp > lastProcessedCmdTime)
                    {
                        lastProcessedCmdTime = msg.timestamp;
                        Debug.Log("[CommandServer] Received command: " + msg.type + " | " + msg.payload);

                        if (msg.type == "toggle_replay")
                        {
                            bool val;
                            if (bool.TryParse(msg.payload, out val))
                                replayActive = val;
                        }
                    }
                }
            }
            else
            {
                Debug.LogWarning("[CommandServer] Command fetch failed: " + req.error);
            }

            yield return new WaitForSeconds(commandPollIntervalSeconds);
        }
    }
}

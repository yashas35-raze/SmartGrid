//using UnityEngine;

//public class SimpleCameraController : MonoBehaviour
//{
//    public float moveSpeed = 10f;
//    public float lookSpeed = 2f;

//    float yaw = 0f;
//    float pitch = 0f;

//    void Update()
//    {
//        // Mouse look
//        yaw += lookSpeed * Input.GetAxis("Mouse X");
//        pitch -= lookSpeed * Input.GetAxis("Mouse Y");
//        pitch = Mathf.Clamp(pitch, -80f, 80f);
//        transform.eulerAngles = new Vector3(pitch, yaw, 0f);

//        // Movement
//        float h = Input.GetAxis("Horizontal");
//        float v = Input.GetAxis("Vertical");

//        Vector3 direction = new Vector3(h, 0, v);
//        transform.Translate(direction * moveSpeed * Time.deltaTime);
//    }
//}

using UnityEngine;

public class KeyboardOnlyCameraController : MonoBehaviour
{
    public float moveSpeed = 10f;
    public float rotationSpeed = 80f;

    void Update()
    {
        // ======================
        // MOVEMENT (WASD)
        // ======================
        float h = Input.GetAxis("Horizontal"); // A / D
        float v = Input.GetAxis("Vertical");   // W / S

        Vector3 move = new Vector3(h, 0, v);
        transform.Translate(move * moveSpeed * Time.deltaTime, Space.Self);

        // ======================
        // ROTATION (KEYBOARD)
        // ======================

        // Left / Right rotation (Yaw)
        if (Input.GetKey(KeyCode.Q))
            transform.Rotate(Vector3.up, -rotationSpeed * Time.deltaTime, Space.World);

        if (Input.GetKey(KeyCode.E))
            transform.Rotate(Vector3.up, rotationSpeed * Time.deltaTime, Space.World);

        // Up / Down rotation (Pitch)
        if (Input.GetKey(KeyCode.R))
            transform.Rotate(Vector3.right, -rotationSpeed * Time.deltaTime, Space.Self);

        if (Input.GetKey(KeyCode.F))
            transform.Rotate(Vector3.right, rotationSpeed * Time.deltaTime, Space.Self);
    }
}


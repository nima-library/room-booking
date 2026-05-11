const booking = JSON.parse(localStorage.getItem("bookingData"));
const detailsDiv = document.getElementById("bookingDetails");
const cancelBtn = document.getElementById("cancelBtn");

const BACKEND_URL = "https://nima-backend.vercel.app";

// ---- show booking details ----
detailsDiv.innerHTML = `
  <p><strong>Leader:</strong> ${booking.leader_name}</p>
  <p><strong>Roll No:</strong> ${booking.leader_roll_no}</p>
  <p><strong>Email:</strong> ${booking.email}</p>
  <p><strong>Room:</strong> ${booking.room_id}</p>
  <p><strong>Date:</strong> ${booking.date}</p>
  <p><strong>Time Slot:</strong> ${booking.time_slot}</p>
  <p><strong>Purpose:</strong> ${booking.purpose}</p>
`;

// ---- check if cancellation allowed ----
function isSlotStarted() {
  const now = new Date();
  const [startTime] = booking.time_slot.split("-");
  const bookingDateTime = new Date(`${booking.date} ${startTime}`);
  return now >= bookingDateTime;
}

if (isSlotStarted()) {
  cancelBtn.disabled = true;
  cancelBtn.innerText = "Cannot cancel (Slot started)";
}

// ---- cancel booking ----
cancelBtn.addEventListener("click", async () => {
  if (!confirm("Are you sure you want to cancel this booking?")) return;

  try {
    const res = await fetch(`${BACKEND_URL}/cancel-booking`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        date: booking.date,
        time_slot: booking.time_slot,
        room_id: booking.room_id
      })
    });

    const result = await res.json();

    if (result.status === "success") {
      localStorage.removeItem("bookingData");
      alert("Booking cancelled");
      window.location.href = "/template/index.html";
    } else {
      alert(result.message);
    }
  } catch (err) {
    alert("Cancel failed. Backend not ready.");
  }
});

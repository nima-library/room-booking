// ✅ CHECK THIS URL (Must match your backend)
const BACKEND_URL = "https://nima-backend.vercel.app"; 

// --- 1. INITIAL SETUP ---
document.addEventListener('DOMContentLoaded', () => {
    // Set default date to today
    const dateInput = document.getElementById('bookingDate');
    const today = new Date().toISOString().split('T')[0];
    dateInput.min = today; 
    dateInput.value = today;

    // Load slots for today immediately
    generateSlots();
    fetchBookedSlots(today);

    // Listen for date changes
    dateInput.addEventListener('change', (e) => {
        // Reset selections when date changes
        selectedSlot = null;
        selectedRoom = null;
        document.querySelectorAll('.selected').forEach(el => el.classList.remove('selected'));
        
        // Fetch new data
        fetchBookedSlots(e.target.value);
    });

    // Listen for group size changes (to show member fields)
    document.getElementById('groupSize').addEventListener('change', updateMemberFields);
});

// --- 2. GLOBAL VARIABLES ---
let selectedSlot = null;
let selectedRoom = null;
let currentBookings = []; // Stores data from server

// ✅ RESTORED ALL 13 ROOMS
const ROOMS = [
    "Discussion Room 1", "Discussion Room 2", "Discussion Room 3", "Discussion Room 4",
    "Discussion Room 5", "Discussion Room 6", "Discussion Room 7", "Discussion Room 8",
    "Discussion Room 9", "Discussion Room 10", "Discussion Room 11", "Discussion Room 12",
    "Discussion Room 13"
];

// --- 3. GENERATE TIME SLOTS (09:00 AM - 05:00 PM) ---
function generateSlots() {
    const grid = document.getElementById('slotGrid');
    grid.innerHTML = ""; // Clear existing

    const times = [
        "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM", "11:00 AM - 12:00 PM",
        "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM", "02:00 PM - 03:00 PM",
        "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM"
    ];

    times.forEach(time => {
        const btn = document.createElement('div');
        btn.className = 'slot-btn free';
        btn.innerText = time;
        btn.onclick = () => selectSlot(btn, time);
        grid.appendChild(btn);
    });
}

// --- 4. FETCH DATA FROM SERVER (Handles "Library Closed" too) ---
async function fetchBookedSlots(dateStr) {
    try {
        const res = await fetch(`${BACKEND_URL}/get-bookings?date=${dateStr}`);
        const data = await res.json();

        // 🛑 CHECK IF LIBRARY IS CLOSED BY ADMIN
        if (data.status === "closed") {
            alert(`⛔ LIBRARY CLOSED: ${data.reason}`);
            
            // Disable everything
            document.querySelectorAll('.slot-btn').forEach(btn => {
                btn.className = 'slot-btn booked'; // Turn grey
                btn.innerHTML += '<br><small style="color:red; font-size:10px;">CLOSED</small>';
                btn.onclick = null; // Remove click
            });
            document.getElementById('roomGrid').innerHTML = "<p style='color:red; text-align:center;'>Library Closed</p>";
            return; // STOP HERE
        }

        // Proceed normally
        currentBookings = data.bookings || [];
        updateSlotAvailability();

    } catch (err) {
        console.error("Error connecting to server:", err);
    }
}

// --- 5. LOGIC: CLICK A SLOT -> SHOW ROOMS ---
function selectSlot(element, time) {
    // 1. Visual selection
    document.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('selected'));
    element.classList.add('selected');
    
    // 2. Save choice
    selectedSlot = time;
    selectedRoom = null; // Reset room when time changes

    // 3. Filter Rooms
    showAvailableRooms(time);
}

// --- 6. SHOW ROOMS BASED ON SELECTED SLOT ---
function showAvailableRooms(slotTime) {
    const roomGrid = document.getElementById('roomGrid');
    roomGrid.innerHTML = ""; // Clear old rooms

    ROOMS.forEach(room => {
        // Check if this specific room is booked at this specific time
        const isBooked = currentBookings.some(b => 
            b.time_slot === slotTime && b.room_id === room
        );

        const btn = document.createElement('button');
        btn.className = isBooked ? 'room-btn room-booked' : 'room-btn';
        btn.innerText = room.replace("Discussion Room ", "Room "); // Shorten name for button
        btn.disabled = isBooked;

        if (!isBooked) {
            btn.onclick = () => {
                // Select Room
                document.querySelectorAll('.room-btn').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                selectedRoom = room; // Save full name
            };
        } else {
             btn.title = "Already Booked";
        }

        roomGrid.appendChild(btn);
    });
}

// --- 7. HELPER: UPDATE SLOT COLORS ---
function updateSlotAvailability() {
    // Reset all slots to free first
    document.querySelectorAll('.slot-btn').forEach(btn => {
        btn.className = 'slot-btn free';
        // Re-attach click listener
        const time = btn.innerText;
        btn.onclick = () => selectSlot(btn, time);
    });

    // Count how many rooms are booked for each slot
    const slotCounts = {};
    currentBookings.forEach(b => {
        slotCounts[b.time_slot] = (slotCounts[b.time_slot] || 0) + 1;
    });

    // If all 13 rooms are taken, mark slot as FULL
    document.querySelectorAll('.slot-btn').forEach(btn => {
        const time = btn.innerText;
        if (slotCounts[time] >= 13) { // Updated check for 13 rooms
            btn.className = 'slot-btn booked';
            btn.onclick = null; // Disable click
            btn.innerHTML = `${time}<br><small style="color:red;">FULL</small>`;
        }
    });
}

// --- 8. GROUP MEMBERS INPUTS ---
function updateMemberFields() {
    const size = document.getElementById('groupSize').value;
    const container = document.getElementById('groupMembersContainer');
    container.innerHTML = ""; // Clear

    for (let i = 1; i < size; i++) { // Start from 1 because Leader is 0
        const div = document.createElement('div');
        div.className = 'member-input-block';
        div.innerHTML = `
            <div class="input-group" style="margin-bottom:10px;">
                <i class="fa-solid fa-user input-icon"></i>
                <input type="text" placeholder="Member ${i + 1} Name" class="mem-name" required>
            </div>
            <div class="input-group">
                <i class="fa-solid fa-id-badge input-icon"></i>
                <input type="text" placeholder="Member ${i + 1} Roll No" class="mem-roll" required>
            </div>
        `;
        container.appendChild(div);
    }
}

// --- 9. FINAL STEP: BOOK THE ROOM ---
async function bookRoom() {
    // 1. Validation
    if (!selectedSlot || !selectedRoom) {
        alert("⚠️ Please select a Time Slot and a Room.");
        return;
    }

    const leaderName = document.getElementById('leaderName').value;
    const rollNo = document.getElementById('rollNo').value;
    const email = document.getElementById('email').value; // ✅ CRITICAL FOR EMAIL
    const dateStr = document.getElementById('bookingDate').value;
    const purpose = document.getElementById('purpose').value;

    if (!leaderName || !rollNo || !email || !purpose) {
        alert("⚠️ Please fill in all details (Name, Roll No, Email, Purpose).");
        return;
    }

    // 2. Gather Member Data
    const members = [];
    document.querySelectorAll('.member-input-block').forEach(block => {
        members.push({
            name: block.querySelector('.mem-name').value,
            roll: block.querySelector('.mem-roll').value
        });
    });

    // 3. Prepare Payload
    const bookingData = {
        room_id: selectedRoom,
        date: dateStr,
        time_slot: selectedSlot,
        leader_name: leaderName,
        leader_roll_no: rollNo,
        email: email, 
        group_size: document.getElementById('groupSize').value,
        members: members,
        purpose: purpose
    };

    // 4. Send to Backend
    const btn = document.getElementById('confirmBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
    btn.disabled = true;

    try {
        const res = await fetch(`${BACKEND_URL}/confirm-booking`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(bookingData)
        });

        const result = await res.json();

        if (result.status === 'success') {
            // Save receipt to local storage for the success page
            localStorage.setItem("bookingReceipt", JSON.stringify(bookingData));
            window.location.href = "success.html"; // Go to receipt
        } else {
            alert("❌ Error: " + result.message);
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    } catch (err) {
        console.error(err);
        alert("❌ Failed to connect to server. Check internet.");
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}
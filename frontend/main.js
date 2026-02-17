// ✅ CHECK THIS URL (Must match your backend)
const BACKEND_URL = "https://nima-backend.vercel.app"; 

// --- 1. INITIAL SETUP ---
document.addEventListener('DOMContentLoaded', () => {
    // Set default date to today
    const dateInput = document.getElementById('bookingDate');
    const today = new Date();
    const localDate = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
    
    dateInput.min = localDate; 
    dateInput.value = localDate;

    // Load slots for today immediately
    generateSlots();
    fetchBookedSlots(localDate);

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

// ✅ ALL 13 ROOMS RESTORED
const ROOMS = [
    "Room 501", "Room 502", "Room 503", "Room 504", "Room 505", "Room 506", "Room 507",
    "Room 601", "Room 602",
    "Room 701", "Room 702",
    "Room 801", "Room 802"
];

// --- 3. GENERATE TIME SLOTS ---
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

// --- 4. FETCH DATA FROM SERVER ---
async function fetchBookedSlots(dateStr) {
    try {
        const res = await fetch(`${BACKEND_URL}/get-bookings?date=${dateStr}`);
        const data = await res.json();

        // 🛑 CHECK IF LIBRARY IS CLOSED BY ADMIN
        if (data.status === "closed") {
            alert(`⛔ LIBRARY CLOSED: ${data.reason}`);
            // Disable everything
            document.querySelectorAll('.slot-btn').forEach(btn => {
                btn.className = 'slot-btn booked'; 
                btn.innerHTML += '<br><small style="color:red; font-size:10px;">CLOSED</small>';
                btn.onclick = null; 
            });
            document.getElementById('roomGrid').innerHTML = "<p style='color:red; text-align:center;'>Library Closed</p>";
            return; 
        }

        // Proceed normally
        currentBookings = data.bookings || [];
        updateSlotAvailability(dateStr); // Pass date to check past times

    } catch (err) {
        console.error("Error connecting to server:", err);
    }
}

// --- 5. SELECTION LOGIC ---
function selectSlot(element, time) {
    // If button is booked or disabled (past time), do nothing
    if (element.classList.contains('booked')) return;

    // Visual selection
    document.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('selected'));
    element.classList.add('selected');
    
    // Save choice
    selectedSlot = time;
    selectedRoom = null; 

    // Filter Rooms
    showAvailableRooms(time);
}

// --- 6. SHOW ROOMS ---
function showAvailableRooms(slotTime) {
    const roomGrid = document.getElementById('roomGrid');
    roomGrid.innerHTML = ""; 

    ROOMS.forEach(room => {
        // Check if this room is booked
        const isBooked = currentBookings.some(b => 
            b.time_slot === slotTime && b.room_id === room
        );

        const btn = document.createElement('button');
        btn.className = isBooked ? 'room-btn room-booked' : 'room-btn';
        btn.innerText = room; 
        btn.disabled = isBooked;

        if (!isBooked) {
            btn.onclick = () => {
                document.querySelectorAll('.room-btn').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                selectedRoom = room; 
            };
        } else {
             btn.title = "Already Booked";
        }

        roomGrid.appendChild(btn);
    });
}

// --- 7. UPDATE SLOTS (PAST TIME & FULL SLOTS) ---
function updateSlotAvailability(selectedDateStr) {
    // 1. Get Current Date/Time Info
    const now = new Date();
    // Construct selected date object to compare
    const selectedDate = new Date(selectedDateStr);
    const isToday = selectedDate.toDateString() === now.toDateString();
    const currentHour = now.getHours();

    // 2. Count bookings per slot
    const slotCounts = {};
    currentBookings.forEach(b => {
        slotCounts[b.time_slot] = (slotCounts[b.time_slot] || 0) + 1;
    });

    // 3. Loop through buttons to disable Past or Full slots
    document.querySelectorAll('.slot-btn').forEach(btn => {
        const timeText = btn.innerText; // e.g., "09:00 AM - 10:00 AM"
        
        // Reset first
        btn.className = 'slot-btn free';
        btn.onclick = () => selectSlot(btn, timeText);

        // --- A. PAST TIME CHECK ---
        if (isToday) {
            const startHour = getStartHour(timeText);
            // If the slot start hour is less than or equal to current hour
            // e.g. if it is 10:18 (hour 10), then 9 (09-10) is past. 
            // 10 (10-11) has already started, so we usually block it too.
            if (startHour <= currentHour) {
                btn.className = 'slot-btn booked';
                btn.onclick = null;
                btn.innerHTML = `${timeText}<br><small style="color:#888;">EXPIRED</small>`;
                return; // Skip full check if expired
            }
        }

        // --- B. FULL SLOT CHECK (13 Rooms) ---
        if (slotCounts[timeText] >= 13) { 
            btn.className = 'slot-btn booked';
            btn.onclick = null; 
            btn.innerHTML = `${timeText}<br><small style="color:red;">FULL</small>`;
        }
    });
}

// Helper to convert "09:00 AM..." to integer 9, "01:00 PM" to 13
function getStartHour(timeString) {
    // Extract "09" and "AM"
    const parts = timeString.split(' - ')[0]; // "09:00 AM"
    let hour = parseInt(parts.split(':')[0]); // 9
    const ampm = parts.split(' ')[1]; // "AM"

    if (ampm === "PM" && hour !== 12) {
        hour += 12;
    }
    if (ampm === "AM" && hour === 12) {
        hour = 0;
    }
    return hour;
}

// --- 8. GROUP MEMBERS INPUTS ---
function updateMemberFields() {
    const size = document.getElementById('groupSize').value;
    const container = document.getElementById('groupMembersContainer');
    container.innerHTML = ""; 

    for (let i = 1; i < size; i++) { 
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

// --- 9. BOOKING FUNCTION ---
async function bookRoom() {
    if (!selectedSlot || !selectedRoom) {
        alert("⚠️ Please select a Time Slot and a Room.");
        return;
    }

    const leaderName = document.getElementById('leaderName').value;
    const rollNo = document.getElementById('rollNo').value;
    const email = document.getElementById('email').value; 
    const dateStr = document.getElementById('bookingDate').value;
    const purpose = document.getElementById('purpose').value;

    if (!leaderName || !rollNo || !email || !purpose) {
        alert("⚠️ Please fill in all details (Name, Roll No, Email, Purpose).");
        return;
    }

    const members = [];
    document.querySelectorAll('.member-input-block').forEach(block => {
        members.push({
            name: block.querySelector('.mem-name').value,
            roll: block.querySelector('.mem-roll').value
        });
    });

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
            localStorage.setItem("bookingReceipt", JSON.stringify(bookingData));
            window.location.href = "success.html"; 
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
const BACKEND_URL = "https://nima-backend.vercel.app"; 

document.addEventListener('DOMContentLoaded', () => {
    const dateInput = document.getElementById('bookingDate');
    const today = new Date();
    
    // Make sure we get the correct local date
    const localTodayStr = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
    
    dateInput.min = localTodayStr; 
    dateInput.value = localTodayStr;

    // Load slots for today 
    fetchBookedSlots(localTodayStr);

    dateInput.addEventListener('change', (e) => {
        selectedSlot = null;
        selectedRoom = null;
        fetchBookedSlots(e.target.value);
    });

    document.getElementById('groupSize').addEventListener('change', updateMemberFields);
});

let selectedSlot = null;
let selectedRoom = null;
let currentBookings = []; 

const ROOMS = [
    "Room 501", "Room 502", "Room 503", "Room 504", "Room 505", "Room 506", "Room 507",
    "Room 601", "Room 602", "Room 701", "Room 702", "Room 801", "Room 802"
];

async function fetchBookedSlots(dateStr) {
    try {
        const res = await fetch(`${BACKEND_URL}/get-bookings?date=${dateStr}`);
        const data = await res.json();

        if (data.status === "closed") {
            alert(`⛔ LIBRARY CLOSED: ${data.reason}`);
            // Completely lock the UI
            const grid = document.getElementById('slotGrid');
            grid.innerHTML = "";
            const times = ["09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM", "11:00 AM - 12:00 PM", "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM", "02:00 PM - 03:00 PM", "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM"];
            times.forEach(t => {
                grid.innerHTML += `<div class="slot-btn booked">${t}<br><small style="color:red; font-size:10px;">CLOSED</small></div>`;
            });
            document.getElementById('roomGrid').innerHTML = "<p style='color:red; text-align:center;'>Library Closed</p>";
            return; 
        }

        currentBookings = data.bookings || [];
        updateSlotAvailability(dateStr); 

    } catch (err) { console.error("Error:", err); }
}

function selectSlot(element, time) {
    if (element.classList.contains('booked')) return;
    document.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('selected'));
    element.classList.add('selected');
    selectedSlot = time;
    selectedRoom = null; 
    showAvailableRooms(time);
}

function showAvailableRooms(slotTime) {
    const roomGrid = document.getElementById('roomGrid');
    roomGrid.innerHTML = ""; 

    ROOMS.forEach(room => {
        const isBooked = currentBookings.some(b => b.time_slot === slotTime && b.room_id === room);
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
        }
        roomGrid.appendChild(btn);
    });
}

// ✅ REWRITTEN TO FIX THE "ALL EXPIRED" BUG
function updateSlotAvailability(selectedDateStr) {
    const grid = document.getElementById('slotGrid');
    grid.innerHTML = ""; // Wipe everything clean first to prevent caching issues
    document.getElementById('roomGrid').innerHTML = ""; // Clear rooms

    const times = [
        "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM", "11:00 AM - 12:00 PM",
        "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM", "02:00 PM - 03:00 PM",
        "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM"
    ];

    const now = new Date();
    const localTodayStr = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
    const currentHour = now.getHours();

    // Count how many rooms are booked per slot
    const slotCounts = {};
    currentBookings.forEach(b => {
        slotCounts[b.time_slot] = (slotCounts[b.time_slot] || 0) + 1;
    });

    times.forEach(timeText => {
        const btn = document.createElement('div');
        btn.className = 'slot-btn free';
        btn.innerHTML = timeText;
        btn.onclick = () => selectSlot(btn, timeText);

        // 1. If user somehow selects a PAST date
        if (selectedDateStr < localTodayStr) {
            btn.className = 'slot-btn booked';
            btn.onclick = null;
            btn.innerHTML = `${timeText}<br><small style="color:#888; font-size:10px;">EXPIRED</small>`;
        } 
        // 2. If user is looking at TODAY
        else if (selectedDateStr === localTodayStr) {
            const startHour = getStartHour(timeText);
            
            // Check if the time has already passed
            if (startHour <= currentHour) {
                btn.className = 'slot-btn booked';
                btn.onclick = null;
                btn.innerHTML = `${timeText}<br><small style="color:#888; font-size:10px;">EXPIRED</small>`;
            } 
            // Check if it's full (all 13 rooms taken)
            else if (slotCounts[timeText] >= 13) {
                btn.className = 'slot-btn booked';
                btn.onclick = null;
                btn.innerHTML = `${timeText}<br><small style="color:red; font-size:10px;">FULL</small>`;
            }
        } 
        // 3. If user is looking at a FUTURE date
        else {
            if (slotCounts[timeText] >= 13) {
                btn.className = 'slot-btn booked';
                btn.onclick = null;
                btn.innerHTML = `${timeText}<br><small style="color:red; font-size:10px;">FULL</small>`;
            }
        }
        grid.appendChild(btn);
    });
}

// Converts "09:00 AM" -> 9, "01:00 PM" -> 13
function getStartHour(timeString) {
    const parts = timeString.split(' - ')[0]; 
    let hour = parseInt(parts.split(':')[0]); 
    const ampm = parts.split(' ')[1]; 
    if (ampm === "PM" && hour !== 12) hour += 12;
    if (ampm === "AM" && hour === 12) hour = 0;
    return hour;
}

function updateMemberFields() {
    const size = document.getElementById('groupSize').value;
    const container = document.getElementById('groupMembersContainer');
    container.innerHTML = ""; 
    for (let i = 1; i < size; i++) { 
        container.innerHTML += `
            <div class="member-input-block">
                <div class="input-group" style="margin-bottom:10px;">
                    <i class="fa-solid fa-user input-icon"></i>
                    <input type="text" placeholder="Member ${i + 1} Name" class="mem-name" required>
                </div>
                <div class="input-group">
                    <i class="fa-solid fa-id-badge input-icon"></i>
                    <input type="text" placeholder="Member ${i + 1} Roll No" class="mem-roll" required>
                </div>
            </div>`;
    }
}

async function bookRoom() {
    if (!selectedSlot || !selectedRoom) return alert("⚠️ Please select a Time Slot and a Room.");
    
    const leaderName = document.getElementById('leaderName').value;
    const rollNo = document.getElementById('rollNo').value;
    const email = document.getElementById('email').value; 
    const dateStr = document.getElementById('bookingDate').value;
    const purpose = document.getElementById('purpose').value;

    if (!leaderName || !rollNo || !email || !purpose) return alert("⚠️ Please fill in all details.");

    const members = [];
    document.querySelectorAll('.member-input-block').forEach(block => {
        members.push({
            name: block.querySelector('.mem-name').value,
            roll: block.querySelector('.mem-roll').value
        });
    });

    const bookingData = { room_id: selectedRoom, date: dateStr, time_slot: selectedSlot, leader_name: leaderName, leader_roll_no: rollNo, email: email, group_size: document.getElementById('groupSize').value, members: members, purpose: purpose };

    const btn = document.getElementById('confirmBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
    btn.disabled = true;

    try {
        const res = await fetch(`${BACKEND_URL}/confirm-booking`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(bookingData) });
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
        alert("❌ Failed to connect to server.");
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}
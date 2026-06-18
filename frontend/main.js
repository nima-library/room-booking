const BACKEND_URL = "https://nima-backend.vercel.app"; 

// --- 1. INITIAL SETUP ---
document.addEventListener('DOMContentLoaded', () => {
    // FIX: We need to pull the email from memory so the form can auto-fill without crashing!
    const studentEmail = localStorage.getItem("studentEmail");
    if (studentEmail) {
        document.getElementById("email").value = studentEmail;
    }

    // Date Setup
    const dateInput = document.getElementById('bookingDate');
    const today = new Date();
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

// 📅 HOLIDAY & WEEKEND CHECKER
function isHoliday(dateObj) {
    const dayOfWeek = dateObj.getDay(); // 0 = Sunday, 6 = Saturday
    
    // Rule: 2nd & 4th Saturdays are closed
    if (dayOfWeek === 6) {
        const date = dateObj.getDate();
        const isSecondSat = date > 7 && date <= 14;
        const isFourthSat = date > 21 && date <= 28;
        if (isSecondSat || isFourthSat) return true;
    }

    return false;
}

async function fetchBookedSlots(dateStr) {
    try {
        const res = await fetch(`${BACKEND_URL}/get-bookings?date=${dateStr}`);
        const data = await res.json();

        if (data.status === "closed") {
            showClosedLibrary(`⛔ LIBRARY CLOSED: ${data.reason}`);
            return; 
        }

        const selectedDateObj = new Date(dateStr);
        if (isHoliday(selectedDateObj)) {
            showClosedLibrary(`⛔ CLOSED: Public Holiday / 2nd or 4th Saturday`);
            return;
        }

        currentBookings = data.bookings || [];
        updateSlotAvailability(dateStr); 

    } catch (err) { console.error("Error:", err); }
}

function showClosedLibrary(message) {
    alert(message);
    const grid = document.getElementById('slotGrid');
    grid.innerHTML = "";
    document.getElementById('roomGrid').innerHTML = "<p style='color:red; text-align:center;'>Library Closed</p>";
}

function selectSlot(element, time) {
    if (element.classList.contains('booked')) return;
    document.querySelectorAll('.slot-btn').forEach(b => b.classList.remove('selected'));
    element.classList.add('selected');
    selectedSlot = time;
    selectedRoom = null; 
    showAvailableRooms(time);
}

// --- 🏨 COMPLEX ROOM RULES ---
function showAvailableRooms(slotTime) {
    const roomGrid = document.getElementById('roomGrid');
    roomGrid.innerHTML = ""; 

    const selectedDateObj = new Date(document.getElementById('bookingDate').value);
    const dayOfWeek = selectedDateObj.getDay();
    const startHour = getStartHour(slotTime);

    let allowedRooms = [...ROOMS];

    // Rule: Sundays ONLY 5th Floor
    if (dayOfWeek === 0) {
        allowedRooms = ROOMS.filter(r => r.includes("50"));
    }
    // Rule: Working Saturdays AFTER 1:30 PM (2:00 PM slot onwards) ONLY 5th & 6th Floor
    if (dayOfWeek === 6 && startHour >= 14) {
        allowedRooms = ROOMS.filter(r => r.includes("50") || r.includes("60"));
    }
    // NEW RULE: 06:00 PM slot ONLY 5th Floor (Regardless of the day)
    if (slotTime === "06:00 PM - 07:45 PM") {
        allowedRooms = allowedRooms.filter(r => r.includes("50"));
    }

    if (allowedRooms.length === 0) {
        roomGrid.innerHTML = "<p style='color:red; font-size:13px;'>No floors available at this time.</p>";
        return;
    }

    allowedRooms.forEach(room => {
        const isBooked = currentBookings.some(b => b.time_slot === slotTime && b.room_id === room);
        const btn = document.createElement('button');
        btn.className = isBooked ? 'room-btn room-booked' : 'room-btn';
        const roomNum = room.replace("Room ", "");
        const floorNum = roomNum.charAt(0);
        btn.innerText = `${floorNum}th Floor ${roomNum}`; 
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

// --- ⏱️ COMPLEX TIMING RULES ---
function updateSlotAvailability(selectedDateStr) {
    const grid = document.getElementById('slotGrid');
    grid.innerHTML = ""; 
    document.getElementById('roomGrid').innerHTML = ""; 

    const times = [
        "08:00 AM - 09:00 AM", "09:00 AM - 10:00 AM", "10:00 AM - 11:00 AM",
        "11:00 AM - 12:00 PM", "12:00 PM - 01:00 PM", "01:00 PM - 02:00 PM",
        "02:00 PM - 03:00 PM", "03:00 PM - 04:00 PM", "04:00 PM - 05:00 PM",
        "05:00 PM - 06:00 PM", "06:00 PM - 07:45 PM"
    ];

    const now = new Date();
    const localTodayStr = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') + '-' + String(now.getDate()).padStart(2, '0');
    const currentHour = now.getHours();

    const selectedDateObj = new Date(selectedDateStr);
    const dayOfWeek = selectedDateObj.getDay();

    const slotCounts = {};
    currentBookings.forEach(b => { slotCounts[b.time_slot] = (slotCounts[b.time_slot] || 0) + 1; });

    times.forEach(timeText => {
        const btn = document.createElement('div');
        btn.className = 'slot-btn free';
        btn.innerHTML = timeText;
        btn.onclick = () => selectSlot(btn, timeText);
        
        const startHour = getStartHour(timeText);

        // Rule: Sundays ONLY 10 AM to 4 PM
        if (dayOfWeek === 0 && (startHour < 10 || startHour >= 16)) {
            btn.className = 'slot-btn booked';
            btn.onclick = null;
            btn.innerHTML = `${timeText}<br><small style="color:#888; font-size:10px;">CLOSED</small>`;
        }
        // Past Dates
        else if (selectedDateStr < localTodayStr) {
            btn.className = 'slot-btn booked';
            btn.onclick = null;
            btn.innerHTML = `${timeText}<br><small style="color:#888; font-size:10px;">EXPIRED</small>`;
        } 
        // Today's Past Hours
        else if (selectedDateStr === localTodayStr && startHour <= currentHour) {
            btn.className = 'slot-btn booked';
            btn.onclick = null;
            btn.innerHTML = `${timeText}<br><small style="color:#888; font-size:10px;">EXPIRED</small>`;
        } 
        // Full Slots
        else if (slotCounts[timeText] >= ROOMS.length) {
            btn.className = 'slot-btn booked';
            btn.onclick = null;
            btn.innerHTML = `${timeText}<br><small style="color:red; font-size:10px;">FULL</small>`;
        }
        
        grid.appendChild(btn);
    });
}

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
    
    // Validate inputs
    const leaderName = document.getElementById('leaderName').value;
    const rollNo = document.getElementById('rollNo').value;
    const email = document.getElementById('email').value; 
    const dateStr = document.getElementById('bookingDate').value;
    const purposeSelect = document.getElementById('purpose').value;
    const contactNo = document.getElementById('contactNo').value;
    const institute = document.getElementById('institute').value;
    const programme = document.getElementById('programme').value;
    const groupSize = document.getElementById('groupSize').value;

    let finalPurpose = purposeSelect;
    if (purposeSelect === "Other") {
        finalPurpose = document.getElementById('otherPurposeText').value;
        if (!finalPurpose) return alert("⚠️ Please specify your 'Other' purpose.");
    }

    if (!leaderName || !rollNo || !email || !finalPurpose || !contactNo || !institute || !programme || !groupSize) {
        return alert("⚠️ Please fill in all details, including dropdown selections.");
    }

    // ✅ STRICT VALIDATION: Ensure all group members are filled out
    const members = [];
    let missingMemberData = false;
    document.querySelectorAll('.member-input-block').forEach(block => {
        const mName = block.querySelector('.mem-name').value.trim();
        const mRoll = block.querySelector('.mem-roll').value.trim();
        if (!mName || !mRoll) missingMemberData = true;
        members.push({ name: mName, roll: mRoll });
    });

    if (missingMemberData) {
        return alert("⚠️ Please fill in the details for all Group Members.");
    }

    const bookingData = { 
        room_id: selectedRoom, 
        date: dateStr, 
        time_slot: selectedSlot, 
        leader_name: leaderName, 
        leader_roll_no: rollNo, 
        email: email, 
        contact_no: contactNo,
        institute: institute,
        programme: programme,
        group_size: groupSize, 
        members: members, 
        purpose: finalPurpose 
    };

    const btn = document.getElementById('confirmBtn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing...';
    btn.disabled = true;

    try {
        const res = await fetch(`${BACKEND_URL}/confirm-booking`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(bookingData) });
        const result = await res.json();
        
        if (result.status === 'success') {
            alert("✅ Booking Confirmed Successfully!\n\nReminder: Please arrive 5 minutes early to your assigned room.");
            localStorage.setItem("bookingData", JSON.stringify(bookingData));
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
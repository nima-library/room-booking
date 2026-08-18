const NIMA_BACKEND_URL = "https://nima-backend.vercel.app";

const NIMA_FIREBASE_CONFIG = {
    apiKey: "AIzaSyBM7-ufYhqO5Uo2PpM-4x_R0sRMCVnQqPE",
    authDomain: "nimalibrary-cbceb.firebaseapp.com",
    databaseURL: "https://nimalibrary-cbceb-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "nimalibrary-cbceb",
    storageBucket: "nimalibrary-cbceb.firebasestorage.app",
    messagingSenderId: "480609468196",
    appId: "1:480609468196:web:5281f1507baaa4780b3db1",
    measurementId: "G-67XY9ZF713"
};

const NIMA_AUTH_KEYS = {
    token: "nimaAppToken",
    role: "nimaUserRole",
    email: "nimaUserEmail",
    studentEmail: "studentEmail"
};

function initNimaFirebaseAuth() {
    if (typeof firebase === "undefined") {
        throw new Error("Firebase Auth SDK not loaded.");
    }
    if (!firebase.apps.length) {
        firebase.initializeApp(NIMA_FIREBASE_CONFIG);
    }
}

function getStoredToken() {
    return localStorage.getItem(NIMA_AUTH_KEYS.token);
}

function getAuthHeaders() {
    const headers = { "Content-Type": "application/json" };
    const token = getStoredToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    return headers;
}

function clearAuthState() {
    Object.values(NIMA_AUTH_KEYS).forEach((key) => localStorage.removeItem(key));
    localStorage.removeItem("staffFloor");
    try {
        if (typeof firebase !== "undefined" && firebase.apps.length) {
            firebase.auth().signOut();
        }
    } catch (err) {
        console.error("Firebase sign-out failed:", err);
    }
}

function routeByRole(role) {
    if (role === "admin") {
        window.location.replace("admin.html");
        return;
    }
    if (role === "staff") {
        window.location.replace("staff.html");
        return;
    }
    window.location.replace("booking.html");
}

async function loginWithGoogle() {
    initNimaFirebaseAuth();

    const provider = new firebase.auth.GoogleAuthProvider();
    const result = await firebase.auth().signInWithPopup(provider);
    const email = (result.user && result.user.email ? result.user.email : "").trim().toLowerCase();
    const idToken = await result.user.getIdToken(true);

    const res = await fetch(`${NIMA_BACKEND_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: idToken })
    });
    const data = await res.json();

    if (data.status !== "success" || !data.token || !data.role) {
        clearAuthState();
        throw new Error(data.message || "Login failed");
    }

    localStorage.setItem(NIMA_AUTH_KEYS.token, data.token);
    localStorage.setItem(NIMA_AUTH_KEYS.role, data.role);
    localStorage.setItem(NIMA_AUTH_KEYS.email, data.email || email);
    if (data.floor) {
        localStorage.setItem("staffFloor", String(data.floor));
    } else {
        localStorage.removeItem("staffFloor");
    }

    if (data.role === "student") {
        localStorage.setItem(NIMA_AUTH_KEYS.studentEmail, data.email || email);
    } else {
        localStorage.removeItem(NIMA_AUTH_KEYS.studentEmail);
    }
    return data;
}

async function verifySession(expectedRole) {
    const token = getStoredToken();
    if (!token) return null;

    try {
        const res = await fetch(`${NIMA_BACKEND_URL}/auth/verify`, {
            headers: { Authorization: `Bearer ${token}` }
        });
        const data = await res.json();

        if (data.status === "success" && data.role) {
            localStorage.setItem(NIMA_AUTH_KEYS.role, data.role);
            if (data.email) localStorage.setItem(NIMA_AUTH_KEYS.email, data.email);
            if (data.floor) {
                localStorage.setItem("staffFloor", String(data.floor));
            }

            if (expectedRole && data.role !== expectedRole) {
                routeByRole(data.role);
                return data;
            }

            return data;
        }
    } catch (err) {
        console.error("Session verification failed:", err);
    }

    clearAuthState();
    return null;
}

function protectPage(expectedRole) {
    const overlay = document.getElementById("loginOverlay");
    verifySession(expectedRole).then((session) => {
        if (!session) {
            if (overlay) overlay.style.display = "flex";
            return;
        }

        if (overlay) overlay.style.display = "none";
    });
}

function logoutAndReturnHome() {
    clearAuthState();
    window.location.replace("index.html");
}

window.NIMAAuth = {
    loginWithGoogle,
    verifySession,
    protectPage,
    getAuthHeaders,
    logoutAndReturnHome,
    routeByRole,
    clearAuthState
};

window.loginWithGoogle = loginWithGoogle;
window.getAuthHeaders = getAuthHeaders;
window.logoutAndReturnHome = logoutAndReturnHome;
window.protectPage = protectPage;

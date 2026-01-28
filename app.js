const API_KEY = 'eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxMTA3MywiZm9yZXZlciI6ZmFsc2UsImlzcyI6Ik9uZU1hcCIsImlhdCI6MTc2OTI1NzU2OCwibmJmIjoxNzY5MjU3NTY4LCJleHAiOjE3Njk1MTY3NjgsImp0aSI6IjdkNGU3N2IyLTk2YmMtNDgyYy1iODVjLWJhYmI3MDc1YTg5YSJ9.JiT7O3-1htxE6NMUnRg9BxjDY-p-yx_erFpUboKLz4zec3r_KpT3SHUH4BQ1YB-XI4-Wmgxtzs7Oxp2KjBCuViJYaf8xdhzA1p7vvJ4Z0Zi7lL3SlKRCQLj5hC6vLhOx_x6-zFvDlyXGue_gqKoBYJEZSJMlH6PMnh5fg6B_lAGjsThiOaswgPHYu9NVOQcNoux4Tpw2VE7H_W1-t0evAk4P3r15zDDI9azLZN16G4SNcqpx1h5ZRzQlgsys4Y-ZJs8DOUOxAMMxd_yllKEm4WxXp1eV9-1X0wn50lu33fjXI2RV3UXQiO7wcd8JxkjFSsonRBR05wmjF3fSGlwmkA';

let students = [];
let map;
let markers = [];

// Initialize map centered on Singapore
function initMap() {
    map = L.map('map').setView([1.3521, 103.8198], 12);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);
}

// Search address using OneMap API
async function searchAddress(searchVal) {
    const url = `https://www.onemap.gov.sg/api/common/elastic/search?searchVal=${encodeURIComponent(searchVal)}&returnGeom=Y&getAddrDetails=Y&pageNum=1`;
    
    try {
        const response = await fetch(url, {
            headers: {
                'Authorization': API_KEY
            }
        });
        
        const data = await response.json();
        
        if (data.found > 0) {
            return data.results[0];
        } else {
            throw new Error('Address not found');
        }
    } catch (error) {
        throw new Error('Failed to search address: ' + error.message);
    }
}

// Add student to list
function addStudent(name, addressData) {
    const student = {
        id: Date.now(),
        name: name,
        address: addressData.ADDRESS,
        postal: addressData.POSTAL,
        latitude: parseFloat(addressData.LATITUDE),
        longitude: parseFloat(addressData.LONGITUDE)
    };
    
    students.push(student);
    addMarker(student);
    updateUI();
    saveToLocalStorage();
}

// Add marker to map
function addMarker(student) {
    const marker = L.marker([student.latitude, student.longitude])
        .addTo(map)
        .bindPopup(`<b>${student.name}</b><br>${student.address}`);
    
    markers.push({ id: student.id, marker: marker });
    
    // Fit map to show all markers
    if (students.length > 0) {
        const bounds = L.latLngBounds(students.map(s => [s.latitude, s.longitude]));
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

// Remove student
function removeStudent(id) {
    students = students.filter(s => s.id !== id);
    
    const markerObj = markers.find(m => m.id === id);
    if (markerObj) {
        map.removeLayer(markerObj.marker);
        markers = markers.filter(m => m.id !== id);
    }
    
    updateUI();
    saveToLocalStorage();
}

// Update UI
function updateUI() {
    document.getElementById('totalStudents').textContent = students.length;
    document.getElementById('busesNeeded').textContent = Math.ceil(students.length / 40);
    
    const listContainer = document.getElementById('studentsList');
    
    if (students.length === 0) {
        listContainer.innerHTML = '<p style="color: #95a5a6; text-align: center;">No students added yet</p>';
        return;
    }
    
    listContainer.innerHTML = students.map(student => `
        <div class="student-item">
            <div class="student-info">
                <div class="student-name">${student.name}</div>
                <div class="student-address">${student.address}</div>
            </div>
            <button class="remove-btn" onclick="removeStudent(${student.id})">Remove</button>
        </div>
    `).join('');
}

// Show message
function showMessage(text, type = 'error') {
    const messageDiv = document.getElementById('message');
    messageDiv.className = type;
    messageDiv.textContent = text;
    
    setTimeout(() => {
        messageDiv.textContent = '';
        messageDiv.className = '';
    }, 3000);
}

// Save to localStorage
function saveToLocalStorage() {
    localStorage.setItem('students', JSON.stringify(students));
}

// Load from localStorage
function loadFromLocalStorage() {
    const saved = localStorage.getItem('students');
    if (saved) {
        students = JSON.parse(saved);
        students.forEach(student => addMarker(student));
        updateUI();
    }
}

// Event listeners
document.getElementById('searchBtn').addEventListener('click', async () => {
    const name = document.getElementById('studentName').value.trim();
    const address = document.getElementById('addressSearch').value.trim();
    
    if (!name) {
        showMessage('Please enter student name', 'error');
        return;
    }
    
    if (!address) {
        showMessage('Please enter address or postal code', 'error');
        return;
    }
    
    const btn = document.getElementById('searchBtn');
    btn.disabled = true;
    btn.textContent = 'Searching...';
    
    try {
        const addressData = await searchAddress(address);
        addStudent(name, addressData);
        
        // Clear inputs
        document.getElementById('studentName').value = '';
        document.getElementById('addressSearch').value = '';
        
        showMessage('Student added successfully!', 'success');
    } catch (error) {
        showMessage(error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Search & Add Student';
    }
});

// Allow Enter key to search
document.getElementById('addressSearch').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        document.getElementById('searchBtn').click();
    }
});

// Initialize
initMap();
loadFromLocalStorage();

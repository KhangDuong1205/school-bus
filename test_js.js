
    // --- Settings Confirmation Logic ---
    let settingsConfirmed = true;

    function markSettingsChanged() {
        settingsConfirmed = false;
        
        // Show confirm button
        const confirmBtn = document.getElementById('confirmSettingsWrapper');
        if (confirmBtn) confirmBtn.style.display = 'block';
        
        // Disable optimization until confirmed
        const optimizeBtn = document.getElementById('optimizeMainBtn');
        if (optimizeBtn) {
            optimizeBtn.disabled = true;
            optimizeBtn.style.background = '#94a3b8'; // greyed out
            optimizeBtn.innerHTML = '<i data-lucide="lock" class="w-4 h-4 text-slate-400"></i> Please Confirm Settings'; lucide.createIcons();
        }
    }

    function confirmSettings() {
        settingsConfirmed = true;
        
        // Hide confirm button
        const confirmBtn = document.getElementById('confirmSettingsWrapper');
        if (confirmBtn) confirmBtn.style.display = 'none';
        
        // Re-enable optimization
        const optimizeBtn = document.getElementById('optimizeMainBtn');
        if (optimizeBtn) {
            optimizeBtn.disabled = false;
            optimizeBtn.style.background = ''; // restore default css
            optimizeBtn.innerHTML = '<i data-lucide="zap" class="w-4 h-4 text-amber-400"></i> Confirm & Optimize'; lucide.createIcons();
            
            // Visual feedback
            optimizeBtn.classList.add('pulse-success');
            setTimeout(() => optimizeBtn.classList.remove('pulse-success'), 1000);
        }
    }

    // Add keydown listener to inputs to trigger enter to confirm
    document.addEventListener('DOMContentLoaded', () => {
        if(typeof lucide !== 'undefined') lucide.createIcons();
        const inputs = ['schoolTime', 'maxRideTime', 'serviceTime', 'avgSpeed'];
        inputs.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                el.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter' && !settingsConfirmed) {
                        confirmSettings();
                    }
                });
            }
        });
    });

    // --- Layout Toggle ---
    function togglePanel() {
        const panel = document.getElementById('controlPanel');
        const panelToggle = document.querySelector('.panel-toggle');
        
        panel.classList.toggle('collapsed');
        
        if (panel.classList.contains('collapsed')) {
            // When collapsed, reset inline styles that might prevent it from collapsing
            panel.dataset.expandedWidth = panel.style.width || '450px';
            panel.dataset.expandedFlexBasis = panel.style.flexBasis || '450px';
            
            panel.style.width = '0';
            panel.style.minWidth = '0';
            panel.style.flexBasis = '0';
            
            if (panelToggle) {
                panelToggle.style.left = '0';
            }
        } else {
            // Restore previous width
            const expandedWidth = panel.dataset.expandedWidth || '450px';
            const expandedFlexBasis = panel.dataset.expandedFlexBasis || '450px';
            
            panel.style.width = expandedWidth;
            panel.style.minWidth = '350px';
            panel.style.flexBasis = expandedFlexBasis;
            
            if (panelToggle) {
                panelToggle.style.left = expandedWidth;
            }
        }

        // Force map resize mainly
        setTimeout(() => {
            if (map) map.invalidateSize();
        }, 300);
    }

    // --- Resizable Sections ---
    // --- Advanced Settings Toggle ---
    function toggleAdvancedSettings() {
        const settings = document.getElementById('advancedSettings');
        const chevron = document.getElementById('advancedChevron');
        settings.classList.toggle('show');
        if (settings.classList.contains('show')) {
            chevron.style.transform = 'rotate(90deg)';
        } else {
            chevron.style.transform = 'rotate(0deg)';
        }
    }

    // --- Update KPI Cards ---
    function updateKPIs(routes) {
        const kpiBuses = document.getElementById('kpiBuses');
        const kpiStudents = document.getElementById('kpiStudents');
        const kpiMaxRide = document.getElementById('kpiMaxRide');
        
        if (!routes || routes.length === 0) {
            kpiBuses.textContent = '–';
            kpiStudents.textContent = '–';
            kpiMaxRide.textContent = '–';
            return;
        }
        
        kpiBuses.textContent = routes.length;
        
        let totalStudents = 0;
        let maxRideTime = 0;
        routes.forEach(r => {
            totalStudents += (r.students || []).length;
            const rideTime = r.max_ride_minutes || r.max_ride_time || 0;
            if (rideTime > maxRideTime) maxRideTime = rideTime;
        });
        
        kpiStudents.textContent = totalStudents;
        kpiMaxRide.textContent = maxRideTime > 0 ? Math.round(maxRideTime) : '–';
    }

    // --- Resizable Sections ---
    function initResizeHandles() {
        const detailsSection = document.querySelector('.section-details'); // No longer exists in the DOM directly like this
        const savedRunsSection = document.getElementById('savedRunsSection');
        const handleSavedRuns = document.getElementById('resizeHandleSaved');
        
        const clusterSection = document.getElementById('clusterListSection');
        const handleClusters = document.getElementById('resizeHandleClusters');
        
        const controlPanel = document.getElementById('controlPanel');
        const horizontalHandle = document.getElementById('horizontalResizeHandle');

        let isResizing = false;
        let isHorizontalResizing = false;
        let startY = 0;
        let startX = 0;
        let startHeight = 0;
        let startWidth = 0;
        let currentTarget = null;

        // Vertical resize for Saved Runs section
        if (handleSavedRuns) {
            handleSavedRuns.addEventListener('mousedown', (e) => {
                isResizing = true;
                currentTarget = savedRunsSection;
                startY = e.clientY;
                startHeight = savedRunsSection.offsetHeight;
                document.body.style.cursor = 'ns-resize';
                document.body.style.userSelect = 'none';
                e.preventDefault();
            });
        }

        // Vertical resize for Cluster section
        if (handleClusters) {
            handleClusters.addEventListener('mousedown', (e) => {
                isResizing = true;
                currentTarget = clusterSection;
                startY = e.clientY;
                startHeight = clusterSection.offsetHeight;
                document.body.style.cursor = 'ns-resize';
                document.body.style.userSelect = 'none';
                e.preventDefault();
            });
        }

        // Horizontal resize for control panel
        horizontalHandle.addEventListener('mousedown', (e) => {
            isHorizontalResizing = true;
            startX = e.clientX;
            // Get actual width from getBoundingClientRect for more accuracy
            startWidth = controlPanel.getBoundingClientRect().width;
            horizontalHandle.classList.add('active-resize');
            controlPanel.style.transition = 'none'; // Disable transition during drag
            
            // Add a style tag to override cursor on entire body to prevent flickering
            const style = document.createElement('style');
            style.id = 'resize-cursor-style';
            style.innerHTML = '* { cursor: ew-resize !important; user-select: none !important; }';
            document.head.appendChild(style);
            
            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (isResizing && currentTarget) {
                // Determine direction of resize based on the target
                // For savedRunsSection, the handle is BELOW it, so dragging down increases height
                // Wait, actually the resize handle is below the savedRunsSection?
                // Let's check the DOM structure:
                // <div id="savedRunsSection">
                // <div id="resizeHandleSaved">
                // If handle is below, dragging down increases height: deltaY is positive
                // Wait, in the DOM the handle is BELOW the section.
                // So dragging down means e.clientY is larger than startY, deltaY is positive, height should INCREASE.
                
                let deltaY = e.clientY - startY;
                
                // If it's the cluster section, its handle is also BELOW it.
                // So deltaY is positive when dragging down.
                
                const newHeight = Math.max(100, Math.min(window.innerHeight * 0.8, startHeight + deltaY));
                currentTarget.style.height = newHeight + 'px';
                currentTarget.style.flex = `0 0 ${newHeight}px`; // Force flex basis to respect the height
            }

            if (isHorizontalResizing) {
                const deltaX = e.clientX - startX;
                const newWidth = Math.max(350, Math.min(window.innerWidth * 0.8, startWidth + deltaX));
                
                // Update width directly
                controlPanel.style.width = newWidth + 'px';
                // Also set max-width to prevent CSS from overriding it if window is resized
                controlPanel.style.maxWidth = 'none';
                controlPanel.style.flexBasis = newWidth + 'px'; // Update flex-basis to ensure it overrides flex constraints
                
                // Move the toggle button to match the new width
                const panelToggle = document.querySelector('.panel-toggle');
                if (panelToggle) {
                    panelToggle.style.transition = 'none';
                    panelToggle.style.left = newWidth + 'px';
                }
                
                // Resize map after panel resize
                if (map) map.invalidateSize();
            }
        });

        document.addEventListener('mouseup', () => {
            if (isResizing || isHorizontalResizing) {
                if (isHorizontalResizing) {
                    horizontalHandle.classList.remove('active-resize');
                    controlPanel.style.transition = ''; // Restore transition
                    
                    // Remove cursor override style
                    const style = document.getElementById('resize-cursor-style');
                    if (style) style.remove();
                    
                    const panelToggle = document.querySelector('.panel-toggle');
                    if (panelToggle) {
                        panelToggle.style.transition = 'left 0.1s ease';
                    }
                }
                isResizing = false;
                isHorizontalResizing = false;
                currentTarget = null;
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                if (map) map.invalidateSize();
            }
        });
    }

    // Call after DOM is loaded
    document.addEventListener('DOMContentLoaded', initResizeHandles);

    // --- Existing App Logic (Copied/Adapted) ---
    let map;
    let markers = {};
    let schoolMarker = null;
    let routeLayers = {}; // Object to store route layers by index
    let clusterCircles = [];
    let pickupMarkers = [];
    let students = []; // Global array to hold student data
    let animationMarkers = {}; // Stores animated bus markers
    let animationTimers = {}; // Stores timers for route animations

    // Global Data Cache
    let optimizedRoutesData = null; // Defined globally
    let currentRoutes = null; // Global variable to hold current routes for export
    let undoStack = []; // Stack for manual drag-and-drop undos
    let isUndoing = false; // Flag to prevent capturing undo events during an undo action

    // Simplified init
    document.addEventListener('DOMContentLoaded', () => {
        if(typeof lucide !== 'undefined') lucide.createIcons();
        initMap();
        loadStudents();
        loadSchool();
        loadFleetInfo();
        loadSavedRuns(); // Load saved runs on init
    });

    // Load fleet summary and update UI
    async function loadFleetInfo() {
        try {
            const res = await fetch('/api/fleet-summary');
            const data = await res.json();

            const infoText = document.getElementById('fleetInfoText');

            if (data.active_vehicles > 0) {
                infoText.innerHTML = `<strong>${data.active_vehicles} buses</strong> available (capacity: ${data.total_capacity} students)`;
            } else {
                infoText.innerHTML = `<span style="color:#b91c1c;">No active vehicles. <a href="/vehicles" style="color:#1d4ed8;">Add vehicles</a></span>`;
            }
        } catch (e) {
            console.error(e);
            document.getElementById('fleetInfoText').innerText = 'Could not load fleet info';
        }
    }


    let drawControl = null;
    let drawnItems = null;

    function initMap() {
        // Center on Singapore
        map = L.map('map', {
            zoomControl: false // Disable default zoom control so we can position it manually
        }).setView([1.3521, 103.8198], 12);
        
        // Add zoom control manually to top-right to avoid overlapping with sidebar toggle
        L.control.zoom({
            position: 'topright'
        }).addTo(map);

        L.tileLayer('https://www.onemap.gov.sg/maps/tiles/Default/{z}/{x}/{y}.png', {
            attribution: '© Singapore Land Authority, OneMap',
            maxZoom: 19
        }).addTo(map);

        // Map events can be added here if needed
    }

    // --- Bulk Assign Logic ---
    let pendingBulkAssignStudents = [];
    let pendingDrawLayer = null;

    function pointInPolygon(point, vs) {
        // ray-casting algorithm
        let x = point[0], y = point[1];
        let inside = false;
        for (let i = 0, j = vs.length - 1; i < vs.length; j = i++) {
            let xi = vs[i][0], yi = vs[i][1];
            let xj = vs[j][0], yj = vs[j][1];
            let intersect = ((yi > y) != (yj > y))
                && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }

    function showBulkAssignModal(students, layer) {
        pendingBulkAssignStudents = students;
        pendingDrawLayer = layer;

        document.getElementById('bulkAssignCount').innerText = students.length;
        
        const select = document.getElementById('bulkAssignBusSelect');
        select.innerHTML = '';
        
        // Populate with existing buses
        optimizedRoutesData.routes.forEach((r, i) => {
            const opt = document.createElement('option');
            opt.value = i;
            let label = r.vehicle_plate && r.vehicle_plate !== 'Pending' ? r.vehicle_plate : `Bus ${i + 1}`;
            opt.innerText = `${label} (${r.students.length} current pax)`;
            select.appendChild(opt);
        });

        // Add option for New Bus
        const newOpt = document.createElement('option');
        newOpt.value = 'new';
        newOpt.innerText = '➕ Create New Bus Route';
        select.appendChild(newOpt);

        document.getElementById('bulkAssignModalOverlay').style.display = 'block';
        document.getElementById('bulkAssignModal').style.display = 'block';
    }

    function closeBulkAssignModal() {
        document.getElementById('bulkAssignModalOverlay').style.display = 'none';
        document.getElementById('bulkAssignModal').style.display = 'none';
        if (pendingDrawLayer && drawnItems) {
            drawnItems.removeLayer(pendingDrawLayer);
        }
        pendingBulkAssignStudents = [];
        pendingDrawLayer = null;
    }

    function confirmBulkAssign() {
        const select = document.getElementById('bulkAssignBusSelect');
        const targetValue = select.value;

        let targetRouteIndex;

        if (targetValue === 'new') {
            // Create a new empty route
            optimizedRoutesData.routes.push({
                students: [],
                vehicle_plate: 'Pending',
                distance_km: 0,
                time_minutes: 0,
                time_violations: []
            });
            targetRouteIndex = optimizedRoutesData.routes.length - 1;
        } else {
            targetRouteIndex = parseInt(targetValue);
        }

        const targetRoute = optimizedRoutesData.routes[targetRouteIndex];
        if (!targetRoute.students) targetRoute.students = [];

        // Move students
        pendingBulkAssignStudents.forEach(item => {
            // 1. Remove from old route
            const oldRoute = optimizedRoutesData.routes[item.currentRouteIndex];
            if (oldRoute && oldRoute.students) {
                oldRoute.students = oldRoute.students.filter(s => s.name !== item.student.name);
            }
            
            // 2. Add to new route
            targetRoute.students.push(item.student);
        });

        // Clean up empty routes (optional, but good UX if an old route is now empty)
        // Actually, let's keep them so the UI doesn't suddenly shift IDs, but empty buses are fine.

        closeBulkAssignModal();

        // 1. Re-render the UI with the new assignments
        displayRoutes(optimizedRoutesData);

        // 2. Immediately trigger recalculation so times and geometry are updated
        applyRouteChanges();
    }

    // --- Core Functions Mapping ---

    async function loadStudents() {
        try {
            const res = await fetch('/api/students');
            const students = await res.json();
            allStudentsData = students;
            addStudentMarkers(students);
            document.getElementById('totalStudents').innerText = students.length;
        } catch (e) { console.error(e); }
    }

    // Global storage for student cluster assignments
    let studentClusterMap = {};  // Maps student name to cluster info
    let allStudentsData = [];    // Store all students for filtering

    function addStudentMarkers(students) {
        // Clear existing
        Object.values(markers).forEach(m => map.removeLayer(m));
        markers = {};

        // Group students by coordinates
        const groupedStudents = {};
        students.forEach(s => {
            const key = `${s.latitude.toFixed(5)},${s.longitude.toFixed(5)}`;
            if (!groupedStudents[key]) groupedStudents[key] = [];
            groupedStudents[key].push(s);
        });

        Object.values(groupedStudents).forEach(group => {
            const count = group.length;
            const s = group[0]; // Use first student for coords/address
            
            let badgeHtml = '';
            if (count > 1) {
                badgeHtml = `<div style="position:absolute; top:-5px; right:-5px; background:#ef4444; color:white; border-radius:50%; width:16px; height:16px; font-size:10px; display:flex; align-items:center; justify-content:center; font-weight:bold; border:1px solid white; z-index:1000;">${count}</div>`;
            }

            const iconHtml = `<div class="custom-student-icon" style="position:relative;">
                <i class="fas fa-user-graduate"></i>
                ${badgeHtml}
            </div>`;

            const marker = L.marker([s.latitude, s.longitude], {
                icon: L.divIcon({
                    className: 'student-marker-container',
                    html: iconHtml,
                    iconSize: [28, 28],
                    iconAnchor: [14, 14],
                    popupAnchor: [0, -14]
                })
            }).addTo(map);

            // Build popup content
            let popupContent = `<b>${s.address || 'Address'}</b><hr style="margin:4px 0; border:0; border-top:1px solid #ccc;">`;
            popupContent += `<ul style="margin:0; padding-left:16px; font-size:0.9rem;">`;
            group.forEach(st => {
                popupContent += `<li>${st.name}</li>`;
            });
            popupContent += `</ul>`;

            marker.bindPopup(popupContent);
            
            // Store marker using the first student's ID or name so it can be referenced
            markers[s.id || s.name] = marker;
            // Also store for other students in the same group so hover/focus logic still works
            if (count > 1) {
                group.forEach(st => {
                    markers[st.id || st.name] = marker;
                });
            }
        });
    }

    async function loadSchool() {
        // Fetch school logic
        const res = await fetch('/api/school');
        const school = await res.json();

        if (school && school.latitude) {
            if (schoolMarker) map.removeLayer(schoolMarker);
            schoolMarker = L.marker([school.latitude, school.longitude], {
                icon: L.divIcon({
                    className: 'school-icon',
                    html: '<div style="font-size:24px;">🏫</div>',
                    iconSize: [30, 30],
                    iconAnchor: [15, 15]
                })
            }).addTo(map);
        }
    }


    // --- Cluster Analysis ---
    // clusterCircles already declared globally above
    const clusterColors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16', '#f97316', '#6366f1'];

    // Helper: Calculate distance in meters between two lat/lng points
    function getDistanceMeters(lat1, lng1, lat2, lng2) {
        const R = 6371000; // Earth's radius in meters
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLng = (lng2 - lng1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLng / 2) * Math.sin(dLng / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    // --- Cluster Visualization State ---
    let clusterLayers = {}; // Map of clusterId -> [layers]
    let isolatedLayers = []; // List of isolated markers

    // Display cluster list in sidebar
    function displayClusterList(data) {
        const section = document.getElementById('clusterListSection');
        const content = document.getElementById('clusterListContent');
        section.style.display = 'flex';

        let html = `<div style="padding: 10px; font-size: 0.85rem;">
            <div style="margin-bottom: 10px; font-weight: 600; display: flex; justify-content: space-between; align-items: center;">
                <span>${data.n_clusters} clusters • ${data.total_students} students</span>
                <label style="font-size: 0.75rem; font-weight: 400; cursor: pointer;">
                    <input type="checkbox" checked onchange="toggleAllClusters(this.checked)"> Show All
                </label>
            </div>`;

        data.clusters.forEach((cluster, i) => {
            const color = clusterColors[i % clusterColors.length];
            const clusterId = i; // Use index as ID

            html += `
                <div style="margin-bottom: 12px; border-left: 4px solid ${color}; padding-left: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div style="font-weight: 600; color: ${color}; cursor: pointer;" onclick="zoomToCluster(${clusterId})">
                            Cluster ${i + 1} (${cluster.size} students)
                        </div>
                        <input type="checkbox" checked onchange="toggleClusterVisibility(${clusterId}, this.checked)" title="Toggle visibility">
                    </div>
                    <div style="font-size: 0.75rem; color: #64748b; margin-bottom: 4px;">
                        ${cluster.distance_from_school} km from school
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                        ${cluster.students.map(s =>
                `<span style="background: ${color}20; color: ${color}; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem;">${s.name}</span>`
            ).join('')}
                    </div>
                </div>`;
        });

        // Isolated students
        if (data.isolated_students && data.isolated_students.length > 0) {
            html += `
                <div style="margin-bottom: 12px; border-left: 4px solid #f59e0b; padding-left: 10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <div style="font-weight: 600; color: #f59e0b;">
                            ⚠️ Isolated (${data.isolated_students.length})
                        </div>
                        <input type="checkbox" checked onchange="toggleIsolatedVisibility(this.checked)">
                    </div>
                    <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                        ${data.isolated_students.map(s =>
                `<span style="background: #fef3c7; color: #b45309; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem;">${s.name}</span>`
            ).join('')}
                    </div>
                </div>`;
        }

        html += '</div>';
        content.innerHTML = html;

        // Populate studentClusterMap for status display in students table
        studentClusterMap = {};  // Reset
        data.clusters.forEach((cluster, i) => {
            cluster.students.forEach(s => {
                studentClusterMap[s.name] = { clusterId: i, clusterSize: cluster.size };
            });
        });

        // Mark isolated students with special cluster ID -1
        data.isolated_students.forEach(s => {
            studentClusterMap[s.name] = { clusterId: -1, isolated: true };
        });

        // Students are now managed on a separate page
    }

    // Toggle visibility for a specific cluster
    function toggleClusterVisibility(clusterId, isVisible) {
        const layers = clusterLayers[clusterId];
        if (layers) {
            layers.forEach(layer => {
                if (isVisible) layer.addTo(map);
                else map.removeLayer(layer);
            });
        }
    }

    // Toggle visibility for isolated students
    function toggleIsolatedVisibility(isVisible) {
        isolatedLayers.forEach(layer => {
            if (isVisible) layer.addTo(map);
            else map.removeLayer(layer);
        });
    }

    // Toggle all
    function toggleAllClusters(isVisible) {
        // Toggle checkboxes
        const checkboxes = document.querySelectorAll('#clusterListContent input[type="checkbox"]');
        checkboxes.forEach(cb => {
            cb.checked = isVisible;
            // Trigger change event logic manually if needed, or just update map directly
        });

        // Update map
        Object.keys(clusterLayers).forEach(id => toggleClusterVisibility(id, isVisible));
        toggleIsolatedVisibility(isVisible);
    }

    // Zoom to cluster
    function zoomToCluster(clusterId) {
        const layers = clusterLayers[clusterId];
        if (layers && layers.length > 0) {
            // Find the circle layer (usually the first one or type L.Circle)
            const circle = layers.find(l => l instanceof L.Circle);
            if (circle) {
                map.fitBounds(circle.getBounds());
            } else {
                // Should replace with actual group bounds
                const group = L.featureGroup(layers);
                map.fitBounds(group.getBounds());
            }
        }
    }

    // Clear cluster visualization
    function clearClusters() {
        // Remove all layers
        Object.values(clusterLayers).forEach(layers => layers.forEach(l => map.removeLayer(l)));
        clusterLayers = {};

        isolatedLayers.forEach(l => map.removeLayer(l));
        isolatedLayers = [];

        document.getElementById('clusterListSection').style.display = 'none';
        // resize handle removed
        document.getElementById('clusterInfoDisplay').style.display = 'none';

        // Reset cluster assignments
        studentClusterMap = {};
    }

    async function analyzeClusters() {
        const btn = document.querySelector('button[onclick="analyzeClusters()"]');
        const infoDisplay = document.getElementById('clusterInfoDisplay');
        const infoContent = document.getElementById('clusterInfoContent');

        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';
        btn.disabled = true;

        // Clear previous clusters
        clearClusters();

        try {
            const res = await fetch('/api/analyze-clusters', { method: 'POST' });
            const data = await res.json();

            if (data.error) {
                alert(data.error);
                return;
            }

            // Draw clusters on map
            data.clusters.forEach((cluster, i) => {
                const color = clusterColors[i % clusterColors.length];

                // Track layers for this cluster
                const layers = [];

                if (cluster.students && cluster.students.length >= 3) {
                    // Create Turf.js FeatureCollection from student coordinates
                    const points = turf.featureCollection(
                        cluster.students.map(s => turf.point([s.lng, s.lat]))
                    );
                    
                    // Generate Convex Hull
                    const hull = turf.convex(points);
                    
                    if (hull) {
                        // Leaflet uses [lat, lng], Turf uses [lng, lat]
                        const latLngs = hull.geometry.coordinates[0].map(coord => [coord[1], coord[0]]);
                        
                        const polygon = L.polygon(latLngs, {
                            color: color,
                            fillColor: color,
                            fillOpacity: 0.15,
                            weight: 2,
                            dashArray: '5, 5'
                        }).addTo(map);
                        layers.push(polygon);
                    }
                } else if (cluster.students && cluster.students.length > 0) {
                    // Fallback to circle if 1 or 2 students (convex hull needs 3 points)
                    let maxDist = 0;
                    cluster.students.forEach(s => {
                        const d = getDistanceMeters(cluster.center.lat, cluster.center.lng, s.lat, s.lng);
                        if (d > maxDist) maxDist = d;
                    });
                    const radius = Math.max(100, (maxDist * 1.2) + 50); // Minimum 100m radius

                    const circle = L.circle([cluster.center.lat, cluster.center.lng], {
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.15,
                        radius: radius,
                        weight: 2,
                        dashArray: '5, 5'
                    }).addTo(map);
                    layers.push(circle);
                }

                const label = L.marker([cluster.center.lat, cluster.center.lng], {
                    icon: L.divIcon({
                        className: 'cluster-label',
                        html: `<div style="background:white; color:${color}; padding:2px 6px; border-radius:12px; border:1px solid ${color}; font-weight:bold; font-size:10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); position:relative; z-index:400;">C${i + 1} (${cluster.students ? cluster.students.length : cluster.size})</div>`,
                        iconSize: [80, 20],
                        iconAnchor: [40, 10]
                    })
                }).addTo(map);
                layers.push(label);

                // Students in this cluster
                cluster.students.forEach(s => {
                    const marker = L.circleMarker([s.lat, s.lng], {
                        radius: 5,
                        fillColor: color,
                        color: '#fff',
                        weight: 1,
                        opacity: 1,
                        fillOpacity: 0.9
                    }).addTo(map);
                    marker.bindPopup(`<b>${s.name}</b><br>Cluster ${i + 1}`);
                    layers.push(marker);
                });

                clusterLayers[i] = layers;
            });

            // Mark isolated students
            data.isolated_students.forEach(s => {
                const marker = L.circleMarker([s.lat, s.lng], {
                    radius: 5,
                    fillColor: '#f59e0b',
                    color: '#fff',
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.9
                }).addTo(map);
                marker.bindPopup(`<b>${s.name}</b><br>Isolated`);
                isolatedLayers.push(marker);
            });

            // Show cluster list
            displayClusterList(data);

            // Update stats panel
            infoDisplay.style.display = 'block';
            infoContent.innerHTML = `
                <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                    <span>Found <strong>${data.n_clusters}</strong> clusters</span>
                    <span>${data.isolated_students.length} isolated</span>
                </div>
            `;

        } catch (e) {
            console.error(e);
            alert('Error analyzing clusters');
        } finally {
            btn.innerHTML = '<i class="fas fa-chart-pie"></i> Analyze Clusters';
            btn.disabled = false;
        }
    }

    // --- Export Logic ---
    let cachedExportData = null;

    async function toggleExportView() {
        const bottomPanel = document.getElementById('exportSection');
        const resizer = document.getElementById('resultResizer');
        const btn = document.getElementById('exportCsvBtn');
        const topPanel = document.getElementById('sectionRoutes');

        const isVisible = bottomPanel.style.display !== 'none';

        if (isVisible) {
            bottomPanel.style.display = 'none';
            resizer.style.display = 'none';
            // Reset top panel to take full height
            topPanel.style.flex = '1';
            btn.innerHTML = '<i data-lucide="list" class="w-4 h-4"></i> View Data'; lucide.createIcons();
            return;
        }

        // Show loading state
        btn.innerHTML = '<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i> Loading...'; lucide.createIcons();

        bottomPanel.style.display = 'flex';
        resizer.style.display = 'flex';
        // Give top panel explicit flex so it can shrink
        topPanel.style.flex = '1';

        // Initialize resizer logic if not already done
        initResizer();

        try {
            // Fetch data if not cached or if needed (for now always fetch to ensure freshness)
            const response = await fetch('/api/export-routes-csv?format=json', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ routes: currentRoutes }) // global variable
            });

            if (!response.ok) throw new Error('Export failed');

            const result = await response.json();
            cachedExportData = result.data;

            renderExportTable(cachedExportData);

        } catch (e) {
            console.error(e);
            alert('Error loading export data: ' + e.message);
            bottomPanel.style.display = 'none';
            resizer.style.display = 'none';
            topPanel.style.flex = '1';
        } finally {
            btn.innerHTML = '<i data-lucide="list" class="w-4 h-4"></i> Hide Data'; lucide.createIcons();
        }
    }

    let resizerInitialized = false;
    function initResizer() {
        if (resizerInitialized) return;

        const resizer = document.getElementById('resultResizer');
        if (!resizer) return; // Add null check

        const topPanel = document.getElementById('sectionRoutes');
        const bottomPanel = document.getElementById('exportSection');
        const container = resizer.parentNode; // #tab-results

        let isResizing = false;

        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = 'row-resize';
            resizer.style.background = '#cbd5e1';
            e.preventDefault(); // Prevent text selection
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;

            const containerRect = container.getBoundingClientRect();
            // Calculate new height for top panel
            // Relative to container top
            let newHeight = e.clientY - containerRect.top;

            // Constrain min/max
            const minHeight = 100;
            const maxTotal = container.clientHeight - 100; // Leave 100px for bottom

            if (newHeight < minHeight) newHeight = minHeight;
            if (newHeight > maxTotal) newHeight = maxTotal;

            // Set explicit height (flex-basis) for top panel
            topPanel.style.flex = `0 0 ${newHeight}px`;
            // Bottom panel takes remaining space
            bottomPanel.style.flex = '1';
        });

        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = 'default';
                resizer.style.background = '#f1f5f9';
            }
        });

        resizerInitialized = true;
    }

    function renderExportTable(data) {
        const tbody = document.getElementById('exportTableBody');
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="padding:8px; text-align:center;">No data available</td></tr>';
            return;
        }

        tbody.innerHTML = data.map(row => `
            <tr style="border-bottom:1px solid #f1f5f9;">
                <td style="padding:4px; font-weight:600; color:#3b82f6;">${row.route_name || '-'}</td>
                <td style="padding:4px; color:#64748b; font-size:0.75rem;">${row.vehicle_id || '-'}</td>
                <td style="padding:4px; font-weight:500;">${row.vehicle_plate || '-'}</td>
                <td style="padding:4px;">${row.student_id}</td>
                <td style="padding:4px;">${Number(row.latitude).toFixed(5)}</td>
                <td style="padding:4px;">${Number(row.longitude).toFixed(5)}</td>
                <td style="padding:4px;">${row.pickup_time}</td>
                <td style="padding:4px;" title="${row.address}" onclick="alert('${row.address}')">${row.postal_code || 'No Postal'}</td>
                <td style="padding:4px;">${row.address_note || '-'}</td>
            </tr>
        `).join('');
    }

    async function downloadCSV() {
        if (!currentRoutes) return;

        try {
            const response = await fetch('/api/export-routes-csv', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ routes: currentRoutes })
            });

            if (!response.ok) throw new Error('Download failed');

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = "optimized_routes.csv";
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

        } catch (e) {
            alert('Download error: ' + e.message);
        }
    }

    // --- Route Toggling ---
    let allRoutesVisible = true;
    let allStudentsVisible = true;

    function toggleAllRoutesVisibility() {
        allRoutesVisible = !allRoutesVisible;
        const btn = document.getElementById('toggleAllRoutesBtn');
        if (btn) {
            btn.innerHTML = allRoutesVisible ? '<i class="fas fa-eye"></i> Routes' : '<i class="fas fa-eye-slash"></i> Routes';
            btn.style.color = allRoutesVisible ? '#3b82f6' : '#94a3b8';
        }

        if (optimizedRoutesData && optimizedRoutesData.routes) {
            optimizedRoutesData.routes.forEach((route, i) => {
                const layer = routeLayers[i];
                const btnIcon = document.getElementById(`eyeBtn-${i}`);
                
                if (layer) {
                    if (allRoutesVisible) {
                        if (!map.hasLayer(layer)) layer.addTo(map);
                    } else {
                        if (map.hasLayer(layer)) map.removeLayer(layer);
                    }
                }
                
                if (btnIcon) {
                    btnIcon.setAttribute('data-lucide', allRoutesVisible ? 'eye' : 'eye-off');
                    btnIcon.parentElement.style.color = allRoutesVisible ? '#3b82f6' : '#94a3b8';
                }
            });
        }
    }

    function toggleAllStudentsVisibility() {
        allStudentsVisible = !allStudentsVisible;
        const btn = document.getElementById('toggleAllStudentsBtn');
        if (btn) {
            btn.innerHTML = allStudentsVisible ? '<i class="fas fa-eye"></i> Students' : '<i class="fas fa-eye-slash"></i> Students';
            btn.style.color = allStudentsVisible ? '#8b5cf6' : '#94a3b8';
        }

        Object.values(markers).forEach(marker => {
            if (allStudentsVisible) {
                if (!map.hasLayer(marker)) marker.addTo(map);
            } else {
                if (map.hasLayer(marker)) map.removeLayer(marker);
            }
        });

        // Also toggle the small pickup markers that are added during routing/animation
        pickupMarkers.forEach(marker => {
            if (allStudentsVisible) {
                if (!map.hasLayer(marker)) marker.addTo(map);
            } else {
                if (map.hasLayer(marker)) map.removeLayer(marker);
            }
        });
    }

    async function fetchAllRealRoutes() {
        if (!optimizedRoutesData || !optimizedRoutesData.routes) return;
        
        const btn = document.getElementById('fetchAllRoutesBtn');
        if (btn) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Fetching...';
            btn.disabled = true;
        }

        const colors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899'];
        
        for (let i = 0; i < optimizedRoutesData.routes.length; i++) {
            const fetchBtn = document.getElementById(`fetchBtn-${i}`);
            // Only fetch if it hasn't been fetched yet (button is still visible)
            if (fetchBtn && fetchBtn.style.display !== 'none') {
                const color = colors[i % colors.length];
                await fetchAndDrawRoute(i, color, true); // pass true for silent mode if needed, but sequential is fine
            }
        }
        
        if (btn) {
            btn.innerHTML = '<i class="fas fa-check"></i> All Fetched';
            setTimeout(() => {
                btn.innerHTML = '<i class="fas fa-route"></i> Fetch All Real Routes';
                btn.disabled = false;
            }, 3000);
        }
    }

    async function fetchAndDrawRoute(index, color, skipEventStop = false) {
        if (!skipEventStop && window.event) window.event.stopPropagation();
        
        const route = optimizedRoutesData && optimizedRoutesData.routes ? optimizedRoutesData.routes[index] : null;
        if (!route) return;

        const btnIcon = document.getElementById(`fetchBtn-${index}`).querySelector('i');
        btnIcon.className = 'fas fa-spinner fa-spin';
        
        try {
            const response = await fetch('/api/fetch-geometry', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    route: route,
                    school_time: document.getElementById('schoolTime').value,
                    max_ride_time: document.getElementById('maxRideTime').value
                })
            });
            const result = await response.json();
            
            if (result.error) {
                alert('Error fetching route: ' + result.error);
                btnIcon.className = 'fas fa-route';
                return;
            }

            const oldTime = route.time_minutes;
            const updatedRoute = result.route;
            // Update the stored data with the new route
            optimizedRoutesData.routes[index] = updatedRoute;
            sessionStorage.setItem('latestRoutes', JSON.stringify(optimizedRoutesData.routes));
            sessionStorage.setItem('optimizedRoutesFullData', JSON.stringify(optimizedRoutesData));
            
            // Update the stats display to show both times distinctly
            const statsDiv = document.getElementById(`route-stats-${index}`);
            if (statsDiv) {
                const hasViolations = updatedRoute.time_violations && updatedRoute.time_violations.length > 0;
                statsDiv.style.color = hasViolations ? '#ef4444' : '#3b82f6';
                statsDiv.innerHTML = `
                    <span style="text-decoration:line-through; opacity:0.5; font-size:0.75rem;" title="Haversine Estimate">${Math.round(oldTime)}m</span> 
                    <span style="color:#f59e0b; font-weight:700;" title="Real Travel Time">${Math.round(updatedRoute.time_minutes)} min</span> 
                    <span style="color:#64748b; font-size:0.8rem; margin-left:4px;">• ${updatedRoute.distance_km.toFixed(1)} km</span>
                `;
            }
            
            // Draw Map Lines
            let routeGeometry = [];
            if (updatedRoute.segments && updatedRoute.segments.length > 0) {
                updatedRoute.segments.forEach(seg => {
                    if (seg.geometry) routeGeometry = routeGeometry.concat(seg.geometry);
                });
            } else if (updatedRoute.geometry) {
                routeGeometry = updatedRoute.geometry;
            }

            if (routeGeometry.length > 0) {
                // Remove old line if exists
                if (routeLayers[index] && map.hasLayer(routeLayers[index])) {
                    map.removeLayer(routeLayers[index]);
                }
                
                const hasRouteViolations = updatedRoute.time_violations && updatedRoute.time_violations.length > 0;
                const lineColor = hasRouteViolations ? '#ef4444' : color;
                
                // Enhance line distinctness: thicker, higher opacity, distinct border wrapper
                const line = L.polyline(routeGeometry, {
                    color: lineColor,
                    weight: 6, // Thicker line
                    opacity: 0.9, // Higher opacity
                    lineCap: 'round',
                    lineJoin: 'round',
                    dashArray: hasRouteViolations ? '10, 10' : null
                }).addTo(map);
                
                // Optional: Add a dark outline to make it stand out against roads
                const outline = L.polyline(routeGeometry, {
                    color: '#000000',
                    weight: 8,
                    opacity: 0.4,
                    lineCap: 'round',
                    lineJoin: 'round',
                    dashArray: hasRouteViolations ? '10, 10' : null
                }).addTo(map);
                
                // Group them so we can toggle both at once
                const layerGroup = L.layerGroup([outline, line]);
                routeLayers[index] = layerGroup;
                layerGroup.addTo(map);
                
                map.fitBounds(line.getBounds(), { padding: [20, 20] });
                
                // Hide the fetch button since it's fetched
                document.getElementById(`fetchBtn-${index}`).style.display = 'none';
                document.getElementById(`eyeBtn-${index}`).className = 'fas fa-eye';
                document.getElementById(`eyeBtn-${index}`).parentElement.style.color = '#3b82f6';
            }
        } catch (err) {
            alert('Failed to fetch route geometry');
            btnIcon.className = 'fas fa-route';
        }
    }

    function toggleRouteVisibility(index) {
        // Stop event from triggering the accordion collapse/expand
        if (window.event) window.event.stopPropagation();
        
        const layer = routeLayers[index];
        const route = optimizedRoutesData && optimizedRoutesData.routes ? optimizedRoutesData.routes[index] : null;
        if (!layer) return;
        
        const btnIcon = document.getElementById(`eyeBtn-${index}`);

        let isNowVisible = false;

        if (map.hasLayer(layer)) {
            map.removeLayer(layer);
            isNowVisible = false;
            if (btnIcon) {
                btnIcon.setAttribute('data-lucide', 'eye-off');
                btnIcon.parentElement.style.color = '#94a3b8';
                lucide.createIcons();
            }
        } else {
            layer.addTo(map);
            isNowVisible = true;
            if (btnIcon) {
                btnIcon.setAttribute('data-lucide', 'eye');
                btnIcon.parentElement.style.color = '#3b82f6';
                lucide.createIcons();
            }
        }

        // Also toggle students for this route
        if (route && route.students) {
            route.students.forEach(s => {
                const marker = markers[s.id || s.name];
                if (marker) {
                    if (isNowVisible) {
                        if (!map.hasLayer(marker)) marker.addTo(map);
                    } else {
                        if (map.hasLayer(marker)) map.removeLayer(marker);
                    }
                }
            });
        }
    }

    // --- Optimization Logic ---
    function restoreCachedRoutes() {
        // Feature removed per user request: Routes are no longer aggressively cached
        // to prevent UI desyncs when the Python server restarts.
    }

    async function optimiseRoutes() {
        const btn = document.querySelector('button[onclick="optimiseRoutes()"]');
        const statusDiv = document.getElementById('optimisationResult');

        // Disable button and show loading state
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Optimizing...';
        btn.disabled = true;
        btn.style.background = '#f59e0b';
        btn.style.animation = 'pulse 1.5s infinite';

        // Show progress updates
        statusDiv.innerHTML = '<span style="color:#f59e0b;">⏳ Step 1/3: Preparing distance and time matrices...</span>';

        // Fake progress updates (since we can't get real progress from backend)
        const progressSteps = [
            { delay: 3000, text: '⏳ Step 2/3: Running Vehicle Routing optimization...' },
            { delay: 8000, text: '⏳ Step 3/3: Fetching real road geometry from OneMap...' }
        ];

        const timeouts = progressSteps.map(step =>
            setTimeout(() => {
                statusDiv.innerHTML = `<span style="color:#f59e0b;">${step.text}</span>`;
            }, step.delay)
        );

        try {
            const res = await fetch('/api/optimise-routes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    school_time: document.getElementById('schoolTime').value,
                    max_ride_time: document.getElementById('maxRideTime').value,
                    service_time: document.getElementById('serviceTime') ? document.getElementById('serviceTime').value : 60,
                    avg_speed: document.getElementById('avgSpeed') ? document.getElementById('avgSpeed').value : 50
                })
            });

            // Clear progress timeouts
            timeouts.forEach(t => clearTimeout(t));

            const result = await res.json();
            if (result.error) {
                statusDiv.innerHTML = `<span style="color:#ef4444;">❌ ${result.error}</span>`;
                return alert(result.error);
            }

            displayRoutes(result);
            document.getElementById('saveRunBtn').disabled = false;
            
            // Show solver parameters in results header
            const solverParamsDisplay = document.getElementById('solverParamsDisplay');
            if (solverParamsDisplay) {
                const avgSpeed = document.getElementById('avgSpeed') ? document.getElementById('avgSpeed').value : 50;
                const serviceTime = document.getElementById('serviceTime') ? document.getElementById('serviceTime').value : 60;
                const maxRideTime = document.getElementById('maxRideTime') ? document.getElementById('maxRideTime').value : 60;
                solverParamsDisplay.innerHTML = `<i class="fas fa-cog"></i> Solving: <b>${avgSpeed}km/h</b>, <b>${serviceTime}s</b>/pax, <b>${maxRideTime}min</b> limit`;
            }
            
            statusDiv.innerHTML = `<span style="color:#10b981;">✅ Optimized! ${result.total_buses} bus(es), ${result.max_route_time_minutes || '?'} min max route</span>`;

            // TWO-STATE WORKFLOW: Switch to Results Mode
            const setupContainer = document.getElementById('setupContainer');
            const resultsHeader = document.getElementById('resultsHeader');
            if (setupContainer && resultsHeader) {
                setupContainer.style.display = 'none';
                resultsHeader.style.display = 'block';
                
                const schoolTime = document.getElementById('schoolTime').value;
                const maxRideTime = document.getElementById('maxRideTime').value;
                const serviceTime = document.getElementById('serviceTime') ? document.getElementById('serviceTime').value : 60;
                
                document.getElementById('resultsSummaryText').innerHTML = `
                    <span><strong>Target:</strong> ${schoolTime}</span>
                    <span><strong>Limit:</strong> ${maxRideTime}m</span>
                    <span><strong>Service:</strong> ${serviceTime}s/pax</span>
                    <span><strong>Result:</strong> ${result.total_buses} Buses</span>
                `;
            }

            // Auto-switch to Results tab (legacy behavior, but we keep it just in case)
            // switchTab('results');

        } catch (e) {
            console.error(e);
            const msg = e.message || e.toString();
            statusDiv.innerHTML = `<span style="color:#ef4444;">❌ Optimization failed: ${msg}</span>`;
            alert(`Optimization failed:\n${msg}\nCheck console for details.`);
        } finally {
            btn.innerHTML = '<i class="fas fa-magic"></i> Confirm & Optimize';
            btn.disabled = false;
            btn.style.background = '';
            btn.style.animation = '';
        }
    }

    function resetToSetup() {
        const setupContainer = document.getElementById('setupContainer');
        const resultsHeader = document.getElementById('resultsHeader');
        const container = document.getElementById('busListsContainer');
        const exportBtn = document.getElementById('exportCsvBtn');
        const saveRunBtn = document.getElementById('saveRunBtn');
        const actionBar = document.getElementById('floatingActionBar');
        const statusDiv = document.getElementById('optimisationResult');
        
        if (setupContainer && resultsHeader) {
            setupContainer.style.display = 'block';
            resultsHeader.style.display = 'none';
        }
        
        // Hide floating action bar
        if (actionBar) actionBar.style.display = 'none';
        
        // Reset status text
        if (statusDiv) statusDiv.innerHTML = 'Ready to optimize.';
        
        // Clear lists
        if (container) {
            container.innerHTML = '<div style="text-align: center; color: #94a3b8; padding: 40px 20px;">Run optimization to see routes here</div>';
        }
        
        // Stop any running animations
        if (typeof animationTimers !== 'undefined') {
            Object.keys(animationTimers).forEach(idx => {
                if (typeof stopRouteAnimation === 'function') stopRouteAnimation(idx);
            });
        }
        
        // Clear map layers
        if (typeof routeLayers !== 'undefined') {
            Object.values(routeLayers).forEach(l => map.removeLayer(l));
            routeLayers = {};
        }
        
        if (typeof pickupMarkers !== 'undefined') {
            pickupMarkers.forEach(m => map.removeLayer(m));
            pickupMarkers = [];
        }
        
        // Reset markers
        if (typeof markers !== 'undefined') {
            Object.values(markers).forEach(m => {
                if (m._icon && m._icon.querySelector('.custom-student-icon')) {
                    m._icon.querySelector('.custom-student-icon').classList.remove('violation');
                }
                m._clickTargets = [];
                
                // Re-bind simple popup without highlight logic
                m.off('click');
                m.on('click', () => {
                    if (typeof m.openPopup === 'function') {
                        m.openPopup();
                    }
                });
            });
        }
        
        // Disable action buttons
        if (exportBtn) exportBtn.disabled = true;
        if (saveRunBtn) saveRunBtn.disabled = true;
        
        // Reset global state
        optimizedRoutesData = null;
        if (typeof currentRoutes !== 'undefined') currentRoutes = [];
        
        // Clear session storage
        sessionStorage.removeItem('latestRoutes');
        sessionStorage.removeItem('optimizedRoutesFullData');
        
        // Recenter map on school
        if (typeof loadSchool === 'function') loadSchool();
    }

    function handleMultipleStudentMarkerClicks(targets) {
        let firstAccordion = null;
        let routeIndices = new Set();

        targets.forEach(target => {
            routeIndices.add(target.routeIndex);
            const accordion = document.getElementById(`route-accordion-${target.routeIndex}`);
            if (accordion) {
                if (accordion.classList.contains('collapsed')) {
                    accordion.classList.remove('collapsed');
                }
                if (!firstAccordion) firstAccordion = accordion;
            }
        });

        // Highlight the routes on the map (highlight all routes that contain these students)
        Object.keys(routeLayers).forEach(idx => {
            const layer = routeLayers[idx];
            const isSelected = routeIndices.has(parseInt(idx));
            if (layer.eachLayer) {
                layer.eachLayer(l => {
                    if (l.setStyle) {
                        const currentWeight = l.options.weight;
                        if (currentWeight > 6) { // Outline
                            l.setStyle({ opacity: isSelected ? 0.6 : 0.1 });
                        } else { // Main line
                            l.setStyle({ opacity: isSelected ? 1.0 : 0.3, weight: isSelected ? 8 : 4 });
                        }
                    }
                });
            } else if (layer.setStyle) {
                layer.setStyle({ opacity: isSelected ? 1.0 : 0.3, weight: isSelected ? 8 : 4 });
            }
        });

        // Highlight the student items in the lists
        setTimeout(() => {
            // Clear any existing highlights
            document.querySelectorAll('.student-drag-item.highlight-student').forEach(el => {
                el.classList.remove('highlight-student');
                el.style.backgroundColor = '';
            });
            
            let firstTargetItem = null;
            
            targets.forEach(target => {
                const accordion = document.getElementById(`route-accordion-${target.routeIndex}`);
                if (accordion) {
                    const items = accordion.querySelectorAll('.student-drag-item');
                    items.forEach(item => {
                        const stData = JSON.parse(item.dataset.studentJson);
                        const namesInGroup = Array.isArray(stData) ? stData.map(s => s.name) : [stData.name];
                        
                        if (namesInGroup.includes(target.studentName)) {
                            item.classList.add('highlight-student');
                            item.style.backgroundColor = '#dbeafe';
                            setTimeout(() => {
                                item.style.backgroundColor = '';
                                item.classList.remove('highlight-student');
                            }, 3000);
                            
                            if (!firstTargetItem) firstTargetItem = item;
                        }
                    });
                }
            });
            
            // Perform smart scrolling specifically inside the routeDetailsContent to the FIRST target
            if (firstTargetItem) {
                const container = document.getElementById('routeDetailsContent');
                if (container) {
                    const containerRect = container.getBoundingClientRect();
                    const itemRect = firstTargetItem.getBoundingClientRect();
                    
                    if (itemRect.top < containerRect.top || itemRect.bottom > containerRect.bottom) {
                        const scrollPos = container.scrollTop + (itemRect.top - containerRect.top) - (containerRect.height / 2) + (itemRect.height / 2);
                        container.scrollTo({
                            top: scrollPos,
                            behavior: 'smooth'
                        });
                    }
                }
            } else if (firstAccordion) {
                firstAccordion.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }, 300);
    }

    function highlightStudentOnMap(lat, lng, studentIdentifier) {
        // Fly to the location smoothly
        map.flyTo([lat, lng], 17, {
            animate: true,
            duration: 1.5
        });

        // Find the marker and open its popup
        // The markers object is keyed by either student.id or student.name
        const marker = markers[studentIdentifier];
        if (marker) {
            // Add a temporary highlight class to the marker's icon if it exists
            if (marker._icon && marker._icon.querySelector('.custom-student-icon')) {
                const iconDiv = marker._icon.querySelector('.custom-student-icon');
                const originalBoxShadow = iconDiv.style.boxShadow;
                
                // Apply a pulsing glow effect
                iconDiv.style.boxShadow = '0 0 0 0 rgba(139, 92, 246, 0.7)';
                iconDiv.animate([
                    { boxShadow: '0 0 0 0 rgba(139, 92, 246, 0.7)' },
                    { boxShadow: '0 0 0 20px rgba(139, 92, 246, 0)' }
                ], {
                    duration: 1500,
                    iterations: 3
                });

                // Open the popup after flying
                setTimeout(() => {
                    if (typeof marker.openPopup === 'function') {
                        marker.openPopup();
                    }
                }, 1500);
            } else {
                // Standard leaflet marker fallback
                setTimeout(() => {
                    if (typeof marker.openPopup === 'function') {
                        marker.openPopup();
                    }
                }, 1500);
            }
        }
    }

    function displayRoutes(data) {
        optimizedRoutesData = data;
        currentRoutes = data.routes; 
        sessionStorage.setItem('latestRoutes', JSON.stringify(data.routes));
        sessionStorage.setItem('optimizedRoutesFullData', JSON.stringify(data));
        
        const container = document.getElementById('routeDetailsContent');
        Object.values(routeLayers).forEach(l => map.removeLayer(l));
        routeLayers = {};
        pickupMarkers.forEach(m => map.removeLayer(m));
        pickupMarkers = [];

        Object.values(markers).forEach(m => {
            if (m._icon && m._icon.querySelector('.custom-student-icon')) {
                m._icon.querySelector('.custom-student-icon').classList.remove('violation');
            }
            m._clickTargets = []; 
        });

        if (!data.routes || data.routes.length === 0) {
            container.innerHTML = '<div class="text-center text-slate-400 py-10 text-sm">No feasible routes found.</div>';
            return;
        }

        const exportBtn = document.getElementById('exportCsvBtn');
        if (exportBtn) exportBtn.disabled = false;
        
        container.innerHTML = `<div id="busListsContainer" class="min-w-[700px]"></div>`;
        const listsContainer = document.getElementById('busListsContainer');
        
        const colors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899'];
        
        data.routes.forEach((route, i) => {
            const color = colors[i % colors.length];
            const hasRouteViolations = route.time_violations && route.time_violations.length > 0;
            const lineColor = hasRouteViolations ? '#ef4444' : color; 

            let routeGeometry = [];
            if (route.segments && route.segments.length > 0) {
                route.segments.forEach(seg => {
                    if (seg.geometry) routeGeometry = routeGeometry.concat(seg.geometry);
                });
            } else if (route.geometry) {
                routeGeometry = route.geometry;
            }

            if (routeGeometry.length > 0) {
                const line = L.polyline(routeGeometry, {
                    color: lineColor, weight: 6, opacity: 0.9, lineCap: 'round', lineJoin: 'round',
                    dashArray: hasRouteViolations ? '10, 10' : null
                }).addTo(map);

                const outline = L.polyline(routeGeometry, {
                    color: '#000000', weight: 8, opacity: 0.4, lineCap: 'round', lineJoin: 'round',
                    dashArray: hasRouteViolations ? '10, 10' : null
                }).addTo(map);

                const layerGroup = L.layerGroup([outline, line]);
                routeLayers[i] = layerGroup;
                layerGroup.addTo(map);
                
                if (i === 0) map.fitBounds(line.getBounds(), { padding: [20, 20] });
            }

            const distKm = route.total_distance_km || route.distance_km || 0;
            const durMin = route.total_duration_minutes || route.time_minutes || 0;
            const students = route.students || [];
            
            let busLabel = `Bus ${i + 1}`;
            if (route.vehicle_plate && route.vehicle_plate !== 'Pending') busLabel = route.vehicle_plate;
            
            let statsHtml = `<span class="mono">${Math.round(durMin)}</span><span class="text-slate-400 ml-1">min</span><span class="text-slate-300 mx-2">|</span><span class="mono">${distKm.toFixed(1)}</span><span class="text-slate-400 ml-1">km</span>`;
            let fetchBtnDisplay = 'block';
            
            if (route.haversine_time_minutes !== undefined) {
                statsHtml = `<span class="mono text-amber-600 font-bold">${Math.round(durMin)}</span><span class="text-slate-400 ml-1">min</span><span class="text-slate-300 mx-2">|</span><span class="mono">${distKm.toFixed(1)}</span><span class="text-slate-400 ml-1">km</span>`;
                fetchBtnDisplay = 'none';
            }

            const lane = document.createElement('div');
            lane.className = 'bus-lane relative border-b-2 border-slate-200 transition-all bg-white';
            lane.id = `route-accordion-${i}`;
            if (i > 0) lane.classList.add('collapsed');

            const header = document.createElement('div');
            header.className = 'flex items-center h-11 px-6 sticky z-10 bg-white/95 cursor-pointer hover:bg-slate-50 transition-colors';
            header.style.top = '0';
            header.onclick = (e) => { if(!e.target.closest('button')) lane.classList.toggle('collapsed'); };
            
            let load = students.length;
            let capacity = route.vehicle_capacity || 40;
            let pct = Math.min(100, (load/capacity)*100);
            let capacityColor = load > capacity ? '#e11d48' : (load === capacity ? '#f59e0b' : color);
            
            header.innerHTML = `
                <div class="absolute left-0 top-0 bottom-0 w-1" style="background: ${lineColor}"></div>
                <button class="w-5 h-5 mr-2 flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded transition-colors chevron-icon">
                    <i data-lucide="chevron-down" class="w-3.5 h-3.5"></i>
                </button>
                <div class="w-2 h-2 rounded-full mr-2.5 ring-2 ring-offset-1" style="background: ${color}; --tw-ring-color: ${color}30;"></div>
                <span class="font-bold text-sm mono tracking-tight text-slate-900">${busLabel}</span>
                <div class="flex items-center gap-3 ml-4 text-xs flex-1">
                    <div class="flex items-center gap-1.5" title="Capacity: ${load}/${capacity}">
                        <i data-lucide="users" class="w-3 h-3 text-slate-400"></i>
                        <span class="mono text-xs capacity-badge ${load > capacity ? 'text-rose-600 font-bold' : 'text-slate-700 font-medium'}" data-bus-index="${i}" data-capacity="${capacity}">${load}/${capacity}</span>
                        <div class="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div class="h-full rounded-full transition-all" style="width: ${pct}%; background: ${capacityColor};"></div>
                        </div>
                    </div>
                    <span class="flex items-center" id="route-stats-${i}">
                        <i data-lucide="clock" class="w-3 h-3 text-slate-400 mr-1"></i>
                        ${statsHtml}
                    </span>
                    ${hasRouteViolations ? '<span class="flex items-center gap-1 px-1.5 py-0.5 bg-rose-50 text-rose-600 rounded text-[10px] font-semibold"><i data-lucide="alert-triangle" class="w-2.5 h-2.5"></i> Over limit</span>' : ''}
                </div>
                <div class="ml-auto flex items-center gap-1">
                    <button onclick="fetchAndDrawRoute(${i}, '${color}')" title="Fetch" id="fetchBtn-${i}" class="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-100 text-amber-500 transition-colors" style="display:${fetchBtnDisplay};"><i data-lucide="zap" class="w-3.5 h-3.5"></i></button>
                    <button onclick="toggleRouteVisibility(${i})" title="Toggle Visibility" id="eyeBtn-${i}" class="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-100 text-blue-500 transition-colors"><i data-lucide="eye" class="w-3.5 h-3.5"></i></button>
                    <button onclick="playRouteAnimation(${i}, '${color}')" title="Play" id="playBtn-${i}" class="w-6 h-6 flex items-center justify-center rounded hover:bg-slate-100 text-emerald-600 transition-colors"><i data-lucide="play" class="w-3.5 h-3.5"></i></button>
                </div>
            `;
            
            const rowsDiv = document.createElement('div');
            rowsDiv.className = 'bus-rows sortable-bus-list';
            rowsDiv.dataset.busIndex = i;
            rowsDiv.style.minHeight = '38px';
            
            if(students.length === 0) {
                rowsDiv.innerHTML = '<div class="h-12 mx-6 my-2 border-2 border-dashed border-slate-200 rounded-lg flex items-center justify-center text-xs text-slate-400">Empty (Drop students here)</div>';
            }
            
            // Group students by exact location
            const locationGroups = {};
            students.forEach(s => {
                const key = `${parseFloat(s.latitude).toFixed(5)},${parseFloat(s.longitude).toFixed(5)}`;
                if (!locationGroups[key]) locationGroups[key] = [];
                locationGroups[key].push(s);
            });
            
            const groupedStudentsList = Object.values(locationGroups);

            groupedStudentsList.forEach((group, stopIdx) => {
                const s = group[0]; // Representative student
                const isViolation = route.time_violations && group.some(st => route.time_violations.some(v => v.student === st.name));
                
                const row = document.createElement('div');
                row.className = 'student-drag-item group border-b border-slate-100 bg-white hover:bg-slate-50 transition-colors';
                
                // Store the ENTIRE group of students for dragging
                row.dataset.studentJson = JSON.stringify(group);
                
                row.style.display = 'grid';
                row.style.gridTemplateColumns = '32px 1fr 130px 70px 100px 40px';
                row.style.alignItems = 'center';
                row.style.minHeight = '38px';
                row.style.paddingTop = group.length > 1 ? '4px' : '0';
                row.style.paddingBottom = group.length > 1 ? '4px' : '0';
                
                if(isViolation) row.style.borderLeft = '3px solid #ef4444';

                // Render Stacked Avatars if multiple
                let avatarsHtml = '';
                const maxAvatars = 3;
                for(let k = 0; k < Math.min(group.length, maxAvatars); k++) {
                    const st = group[k];
                    const initials = st.name.split(' ').map(n=>n[0]).slice(0,2).join('');
                    avatarsHtml += `<div class="w-5 h-5 shrink-0 rounded-full flex items-center justify-center text-[9px] font-bold text-white shadow-sm ring-2 ring-white" style="background: linear-gradient(135deg, ${color}, ${color}cc); margin-left: ${k > 0 ? '-8px' : '0'}; z-index: ${maxAvatars - k};">${initials}</div>`;
                }
                if (group.length > maxAvatars) {
                    avatarsHtml += `<div class="w-5 h-5 shrink-0 rounded-full flex items-center justify-center text-[8px] font-bold text-slate-600 bg-slate-100 shadow-sm ring-2 ring-white" style="margin-left: -8px; z-index: 0;">+${group.length - maxAvatars}</div>`;
                }

                const namesHtml = group.map(st => {
                    const stViolation = route.time_violations && route.time_violations.some(v => v.student === st.name);
                    return `<span class="inline-block px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded text-[10px] font-semibold border border-slate-200 whitespace-nowrap mr-1 mt-1 ${stViolation ? 'border-rose-300 bg-rose-50 text-rose-700' : ''}">${st.name}</span>`;
                }).join('');

                const gradeStr = s.grade || 'P'+Math.floor(Math.random()*6 + 1);

                row.innerHTML = `
                    <div class="px-2 flex justify-center h-full items-center">
                        <div class="drag-handle w-6 h-6 flex items-center justify-center text-slate-300 group-hover:text-slate-600 hover:!text-slate-900 hover:bg-slate-200 rounded transition-colors" title="Drag ${group.length} students"><i data-lucide="grip-vertical" class="w-3.5 h-3.5"></i></div>
                    </div>
                    <div class="pr-2 min-w-0 py-1" style="cursor:pointer;" onclick="highlightStudentOnMap(${s.latitude}, ${s.longitude}, '${s.id || s.name.replace(/'/g, "\'")}')">
                        <div class="flex items-center gap-2 min-w-0 mb-1">
                            <div class="flex items-center">${avatarsHtml}</div>
                            <div class="flex flex-col min-w-0">
                                <span class="text-sm font-semibold ${isViolation?'text-rose-600':'text-slate-800'} truncate leading-tight flex items-center gap-1">${group.length > 1 ? group.length + ' Students' : s.name} ${isViolation?'<i data-lucide="alert-triangle" class="w-3 h-3 text-rose-500"></i>':''}</span>
                                <span class="text-[10px] text-slate-500 truncate mono leading-tight">${s.address}</span>
                            </div>
                        </div>
                        ${group.length > 1 ? `<div class="flex flex-wrap w-full">${namesHtml}</div>` : ''}
                    </div>
                    <div class="text-xs mono text-slate-500 truncate pr-2">${s.phone || '-'}</div>
                    <div class="text-center">
                        <span class="inline-flex items-center px-1.5 py-0.5 text-[10px] font-bold rounded mono bg-slate-100 text-slate-600">${group.length > 1 ? 'MIX' : gradeStr}</span>
                    </div>
                    <div class="text-xs mono ${isViolation?'text-rose-600 font-bold':'text-slate-600'} text-right pr-3">${s.pickup_time || '-'}</div>
                    <div class="text-center h-full flex items-center justify-center">
                        <button onclick="unassignStudent(this, event)" class="w-5 h-5 flex items-center justify-center text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-all rounded bg-white hover:bg-rose-50" title="Unassign ${group.length} students"><i data-lucide="x" class="w-3 h-3"></i></button>
                    </div>
                `;
                rowsDiv.appendChild(row);

                // Highlight markers on map for ALL students in this group
                group.forEach(st => {
                    const marker = markers[st.id || st.name];
                    if(marker) {
                        if (!marker._clickTargets) marker._clickTargets = [];
                        marker._clickTargets.push({ routeIndex: i, studentName: st.name });
                        marker.off('click');
                        marker.on('click', () => { handleMultipleStudentMarkerClicks(marker._clickTargets); if(marker.openPopup) marker.openPopup(); });
                        if(isViolation) {
                            if(marker._icon && marker._icon.querySelector('.custom-student-icon')) marker._icon.querySelector('.custom-student-icon').classList.add('violation');
                        }
                    }
                });
            });

            lane.appendChild(header);
            lane.appendChild(rowsDiv);
            listsContainer.appendChild(lane);

            new Sortable(rowsDiv, {
                group: 'shared-buses', animation: 150, handle: '.drag-handle', ghostClass: 'opacity-50',
                onEnd: handleDragEnd
            });
        });

        const unassignedLane = document.createElement('div');
        unassignedLane.className = 'bus-lane relative border-b-2 border-slate-200 bg-amber-50/30';
        unassignedLane.innerHTML = `
            <div class="flex items-center h-11 px-6 sticky z-10 bg-amber-50/80 border-l-4 border-amber-400 cursor-pointer" style="top:0" onclick="this.parentElement.classList.toggle('collapsed')">
                <button class="w-5 h-5 mr-2 flex items-center justify-center text-amber-700 hover:bg-amber-100 rounded transition-colors chevron-icon"><i data-lucide="chevron-down" class="w-3.5 h-3.5"></i></button>
                <i data-lucide="alert-triangle" class="w-3.5 h-3.5 text-amber-600 mr-2"></i>
                <span class="font-bold text-sm text-amber-900">Unassigned students</span>
                <span class="ml-3 mono text-xs font-bold text-amber-700" id="unassignedCountBadge">0</span>
            </div>
            <div id="unassignedList" class="bus-rows sortable-bus-list" data-bus-index="-1" style="min-height:60px;">
                <div id="unassignedEmptyText" class="h-12 mx-6 my-2 border-2 border-dashed border-amber-200 rounded-lg flex items-center justify-center text-xs text-amber-600/70">Drop students here to unassign</div>
            </div>
        `;
        listsContainer.appendChild(unassignedLane);

        new Sortable(document.getElementById('unassignedList'), {
            group: 'shared-buses', animation: 150, handle: '.drag-handle', ghostClass: 'opacity-50',
            onEnd: handleDragEnd
        });

        if(typeof lucide !== 'undefined') lucide.createIcons();
        document.getElementById('optimisationResult').innerText = `Generated ${data.routes.length} routes covering ${data.total_students} students.`;
    }
    
    function unassignSingleStudent(btnElement, studentId, event, isHeader = false) {
        if (isUndoing) return;
        if (event) event.stopPropagation();

        const item = btnElement.closest('.student-drag-item');
        const fromList = item.parentElement;
        
        let group = JSON.parse(item.dataset.studentJson);
        const studentIdx = group.findIndex(s => (s.id || s.name) === studentId);
        
        if (studentIdx === -1) return;
        
        // Remove student from group array
        const removedStudent = group.splice(studentIdx, 1)[0];
        
        // Save action for undo
        saveAction({
            type: 'unassignSingle',
            student: removedStudent,
            groupJson: JSON.stringify(JSON.parse(item.dataset.studentJson)),
            fromListId: fromList.id,
            fromBusIndex: fromList.dataset.busIndex,
            parentItem: item
        });
        
        // Handle UI update based on remaining group size
        if (group.length === 0) {
            // Group empty, move the whole item to unassigned (or just remove it)
            // It shouldn't happen usually since we remove single ones. But just in case.
            const unassignedList = document.getElementById('unassignedList');
            unassignedList.appendChild(item);
        } else {
            // Update group dataset
            item.dataset.studentJson = JSON.stringify(group);
            
            if (isHeader) {
                // If they removed the header student, promote the next student to header
                const newHeader = group[0];
                item.querySelector('.group-header-name').innerText = newHeader.name;
                
                // Remove the promoted student from the sub-list UI
                const subLists = item.querySelectorAll('#group-' + fromList.dataset.busIndex + '-[0-9]+ div');
                // The structure is nested, so we just remove the first row of the sublist
                const subListContainer = item.querySelector('[id^="group-"]');
                if (subListContainer && subListContainer.firstElementChild) {
                    subListContainer.removeChild(subListContainer.firstElementChild);
                }
            } else {
                // Just remove the row from the sub-list UI
                btnElement.closest('div[style*="display:flex"]').remove();
            }
            
            // Update the "X more" button text
            const expandBtn = item.querySelector('button[onclick*="display"]');
            if (expandBtn) {
                if (group.length > 1) {
                    const isExpanded = expandBtn.querySelector('i').classList.contains('fa-chevron-up');
                    expandBtn.innerHTML = `<i data-lucide="chevron-${isExpanded ? 'up' : 'down'}" class="w-3 h-3"></i> ${group.length - 1} more`; lucide.createIcons();
                } else {
                    expandBtn.remove();
                }
            }
        }
        
        // Create a new independent item for the unassigned student
        const unassignedList = document.getElementById('unassignedList');
        const newItem = document.createElement('div');
        newItem.className = 'student-drag-item';
        newItem.dataset.studentJson = JSON.stringify([removedStudent]);
        newItem.innerHTML = `
            <div class="drag-handle" title="Drag to reorder">⋮⋮</div>
            <div style="flex:1;">
                <div style="font-size:0.9rem; color:#1e293b;"><span style="font-weight:700;">${removedStudent.name}</span></div>
                <div style="font-size:0.75rem; color:#64748b; margin-top:2px;">${removedStudent.address}</div>
            </div>
            <div style="display:flex; align-items:center; gap:8px;">
                <div class="time-pill">-</div>
                <button onclick="unassignStudent(this)" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:1rem;" title="Unassign">
                    <i data-lucide="x" class="w-3.5 h-3.5"></i>
                </button>
            </div>
        `;
        unassignedList.appendChild(newItem);

        // Mark settings as changed and show toast
        markSettingsChanged();
        showUndoToast('Removed student from group');
        
        // Re-evaluate limits
        evaluateCapacityLimits();
    }

    function unassignStudent(btnElement) {
        if (isUndoing) return;

        const item = btnElement.closest('.student-drag-item');
        const fromList = item.parentElement;
        const sibling = item.nextElementSibling; // Store to insert back precisely
        const unassignedList = document.getElementById('unassignedList');

        // Add to undo stack
        undoStack.push({
            type: 'unassign',
            item: item,
            from: fromList,
            sibling: sibling
        });
        document.getElementById('undoBtn').style.display = 'inline-block';

        // Remove empty text if needed
        const emptyText = document.getElementById('unassignedEmptyText');
        if (emptyText) emptyText.style.display = 'none';

        // Move to unassigned list
        unassignedList.appendChild(item);

        // Check if from list became empty
        const emptyTextFrom = fromList.querySelector('div[style*="text-align:center"]');
        if (emptyTextFrom && fromList.querySelectorAll('.student-drag-item').length === 0) {
            emptyTextFrom.style.display = 'block';
        }

        // Trigger action bar
        document.getElementById('floatingActionBar').style.display = 'flex';
        updateUnassignedCount();
        checkCapacities();
    }

    function handleDragEnd(evt) {
        if (isUndoing) return;

        // Add to undo stack
        if (evt.from !== evt.to || evt.oldIndex !== evt.newIndex) {
            undoStack.push({
                type: 'drag',
                item: evt.item,
                from: evt.from,
                to: evt.to,
                oldIndex: evt.oldIndex,
                newIndex: evt.newIndex,
                sibling: evt.item.nextElementSibling // Note: nextSibling after move might not be original, but Sortable handles it if we just use indices, or we store the original sibling during onStart. We'll use insertBefore with the specific lists.
            });
            document.getElementById('undoBtn').style.display = 'inline-block';
        }

        document.getElementById('floatingActionBar').style.display = 'flex';

        const emptyText = evt.to.querySelector('div[style*="text-align:center"]');
        if (emptyText && evt.to.querySelectorAll('.student-drag-item').length > 0) {
            emptyText.style.display = 'none';
        }

        const emptyTextFrom = evt.from.querySelector('div[style*="text-align:center"]');
        if (emptyTextFrom && evt.from.querySelectorAll('.student-drag-item').length === 0) {
            emptyTextFrom.style.display = 'block';
        }

        updateUnassignedCount();
        checkCapacities();
    }

    function undoLastAction() {
        if (undoStack.length === 0) return;

        isUndoing = true; // Prevent triggering events
        const action = undoStack.pop();

        if (action.type === 'drag') {
            // Move item back
            const targetItems = Array.from(action.from.children);
            // Insert at the old index. If oldIndex > current items, append.
            // Note: Sortable JS elements include the 'emptyText' div, so indices might be off.
            // Using insertBefore or appendChild directly.
            if (action.from.children.length > action.oldIndex) {
                action.from.insertBefore(action.item, action.from.children[action.oldIndex]);
            } else {
                action.from.appendChild(action.item);
            }

            // Fix empty texts
            const emptyTextTo = action.to.querySelector('div[style*="text-align:center"]');
            if (emptyTextTo && action.to.querySelectorAll('.student-drag-item').length === 0) {
                emptyTextTo.style.display = 'block';
            }
            const emptyTextFrom = action.from.querySelector('div[style*="text-align:center"]');
            if (emptyTextFrom && action.from.querySelectorAll('.student-drag-item').length > 0) {
                emptyTextFrom.style.display = 'none';
            }

        } else if (action.type === 'unassign') {
            if (action.sibling && action.from.contains(action.sibling)) {
                action.from.insertBefore(action.item, action.sibling);
            } else {
                action.from.appendChild(action.item);
            }

            // Fix empty texts
            const emptyTextTo = document.getElementById('unassignedEmptyText');
            if (emptyTextTo && document.getElementById('unassignedList').querySelectorAll('.student-drag-item').length === 0) {
                emptyTextTo.style.display = 'block';
            }
            const emptyTextFrom = action.from.querySelector('div[style*="text-align:center"]');
            if (emptyTextFrom && action.from.querySelectorAll('.student-drag-item').length > 0) {
                emptyTextFrom.style.display = 'none';
            }
        }

        checkCapacities();
        updateUnassignedCount();

        if (undoStack.length === 0) {
            document.getElementById('undoBtn').style.display = 'none';
            // Optional: Hide action bar if no changes remain (but we don't track absolute state diff, so leave it visible until apply)
        }

        isUndoing = false;
    }

    function checkCapacities() {
        let hasOvercapacity = false;
        const lists = document.querySelectorAll('.sortable-bus-list');

        lists.forEach(list => {
            const busIndex = list.dataset.busIndex;
            if (busIndex === '-1') return; // Skip unassigned

            let count = 0;
            list.querySelectorAll('.student-drag-item').forEach(item => {
                const data = JSON.parse(item.dataset.studentJson);
                count += Array.isArray(data) ? data.length : 1;
            });

            const badge = document.querySelector(`.capacity-badge[data-bus-index="${busIndex}"]`);
            if (badge) {
                const max = parseInt(badge.dataset.capacity);
                badge.innerText = `${count} / ${max} pax`;
                if (count > max) {
                    badge.style.color = 'white';
                    badge.style.background = '#ef4444';
                    hasOvercapacity = true;
                } else {
                    badge.style.color = '#475569';
                    badge.style.background = '#f1f5f9';
                }
            }
        });

        const recalcBtn = document.getElementById('recalcRoutesBtn');
        if (recalcBtn) {
            if (hasOvercapacity) {
                recalcBtn.disabled = true;
                recalcBtn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Overcapacity';
                recalcBtn.style.background = '#94a3b8';
            } else {
                recalcBtn.disabled = false;
                recalcBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Apply & Recalculate';
                recalcBtn.style.background = '#f59e0b';
            }
        }
    }    
    function updateUnassignedCount() {
        const unassignedList = document.getElementById('unassignedList');
        if (!unassignedList) return;
        let count = unassignedList.querySelectorAll('.student-drag-item').length;
        const txt = document.getElementById('unassignedCountText');
        const badge = document.getElementById('unassignedCountBadge');
        if(txt) txt.innerText = count > 0 ? `${count} unsaved changes` : 'Unsaved changes';
        if(badge) badge.innerText = count;
        
        const emptyText = document.getElementById('unassignedEmptyText');
        if (emptyText) emptyText.style.display = count === 0 ? 'flex' : 'none';
    }

    // --- RECALCULATE LOGIC ---
    async function applyRouteChanges() {
        const btn = document.getElementById('recalcRoutesBtn');
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Recalculating...';
        btn.disabled = true;

        // Reconstruct routes object from DOM
        const newRoutes = [];
        const lists = document.querySelectorAll('.sortable-bus-list');
        
        lists.forEach((list, i) => {
            const busIndex = list.dataset.busIndex;
            if (busIndex === '-1') return; // Skip unassigned bucket
            
            const originalRoute = optimizedRoutesData.routes[busIndex];
            if (!originalRoute) return;
            
            const routeCopy = { ...originalRoute, students: [] };
            
            const items = list.querySelectorAll('.student-drag-item');
            items.forEach(item => {
                const groupData = JSON.parse(item.dataset.studentJson);
                if (Array.isArray(groupData)) {
                    routeCopy.students.push(...groupData);
                } else {
                    routeCopy.students.push(groupData);
                }
            });
            
            routeCopy.student_count = routeCopy.students.length;
            newRoutes.push(routeCopy);
        });

        try {
            const res = await fetch('/api/recalculate-routes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    routes: newRoutes,
                    school_time: document.getElementById('schoolTime').value,
                    max_ride_time: document.getElementById('maxRideTime').value
                })
            });

            const result = await res.json();
            if (result.error) throw new Error(result.error);
            
            // Update global data and re-render
            optimizedRoutesData.routes = result.routes;
            displayRoutes(optimizedRoutesData);
            
            alert('Routes updated successfully!');
            
        } catch (e) {
            console.error(e);
            alert('Failed to recalculate: ' + e.message);
        } finally {
            btn.innerHTML = '<i data-lucide="check-circle-2" class="w-3 h-3"></i> Apply & Recalculate'; lucide.createIcons();
            btn.disabled = false;
            document.getElementById('floatingActionBar').style.display = 'none'; // Hide floating bar
        }
    }

    function stopRouteAnimation(index) {
        if (animationTimers[index]) {
            clearInterval(animationTimers[index]);
            delete animationTimers[index];
        }
        if (animationMarkers[index]) {
            map.removeLayer(animationMarkers[index]);
            delete animationMarkers[index];
        }
        document.getElementById(`playBtn-${index}`).className = 'fas fa-play-circle';
        document.getElementById(`playBtn-${index}`).parentElement.style.color = '#10b981';
    }

    function playRouteAnimation(index, color) {
        // Toggle if currently playing
        if (animationTimers[index]) {
            stopRouteAnimation(index);
            return;
        }

        const route = optimizedRoutesData.routes[index];
        let pathCoords = [];
        
        // Flatten geometry into array of points
        if (route.segments && route.segments.length > 0) {
            route.segments.forEach(seg => {
                if (seg.geometry) pathCoords = pathCoords.concat(seg.geometry);
            });
        } else if (route.geometry) {
            pathCoords = route.geometry;
        }

        if (pathCoords.length === 0) return alert('No geometry available to animate.');

        // Setup Marker
        const busIcon = L.divIcon({
            html: `🚐`,
            className: 'bus-icon',
            iconSize: [28, 28],
            iconAnchor: [14, 14],
        });

        const marker = L.marker(pathCoords[0], { icon: busIcon, zIndexOffset: 1000 }).addTo(map);
        animationMarkers[index] = marker;

        // Change button to stop state
        const btnIcon = document.getElementById(`playBtn-${index}`);
        btnIcon.className = 'fas fa-stop-circle';
        btnIcon.parentElement.style.color = '#ef4444';

        // Animation Loop
        let frame = 0;
        const totalFrames = pathCoords.length;
        // Adjust speed based on route length to keep duration reasonable
        const delay = Math.max(10, Math.floor(5000 / totalFrames)); 

        animationTimers[index] = setInterval(() => {
            if (frame >= totalFrames) {
                stopRouteAnimation(index);
                return;
            }
            
            const point = pathCoords[frame];
            marker.setLatLng(point);
            
            // Check if we are near any pickup location to show a brief popup
            if (frame % 20 === 0 && route.students) {
                for(let s of route.students) {
                    // Quick distance check (approximate)
                    const dlat = Math.abs(point[0] - s.latitude);
                    const dlng = Math.abs(point[1] - s.longitude);
                    if (dlat < 0.001 && dlng < 0.001) {
                        marker.bindPopup(`<b>Pickup:</b> ${s.name}<br><b>Time:</b> ${s.pickup_time || '-'}`).openPopup();
                        setTimeout(() => marker.closePopup(), 1500);
                        break;
                    }
                }
            }

            frame += 2; // skip frames to speed up animation nicely
        }, delay);
    }

    function clearRouteLines() {
        // Stop any running animations
        Object.keys(animationTimers).forEach(idx => stopRouteAnimation(idx));
        
        Object.values(routeLayers).forEach(l => map.removeLayer(l));
        routeLayers = {};
        pickupMarkers.forEach(m => map.removeLayer(m));
        pickupMarkers = [];
        optimizedRoutesData = null;
        currentRoutes = null;
        document.getElementById('routeDetailsContent').innerHTML = '<div style="text-align: center; color: #94a3b8; padding-top: 20px;">Routes cleared.</div>';
    }

    async function saveCurrentRun() {
        if (!optimizedRoutesData) return;
        const res = await fetch('/api/runs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ result_json: optimizedRoutesData })
        });
        const data = await res.json();
        if (data.success) {
            alert('Run saved!');
            loadSavedRuns(); // Refresh list
        }
    }

    // --- Saved Runs Logic ---
    async function loadSavedRuns() {
        const container = document.getElementById('savedRunsContent');
        if (!container) return;

        container.innerHTML = '<div style="text-align: center; color: #94a3b8; padding-top: 20px;">Loading...</div>';

        try {
            const res = await fetch('/api/runs');
            const runs = await res.json();

            if (runs.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: #94a3b8; padding-top: 20px;">No saved runs.</div>';
                return;
            }

            container.innerHTML = runs.map(run => `
                <div class="route-item" style="border-left: 3px solid #10b981; background: #fff;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px;">
                        <div style="font-weight:600; color:#334155; font-size:0.85rem;">${run.name}</div>
                        <div style="font-size:0.7rem; color:#94a3b8;">${new Date(run.timestamp).toLocaleDateString()}</div>
                    </div>
                    <div style="font-size:0.75rem; color:#64748b; margin-bottom:8px;">
                        ${run.summary}
                    </div>
                    <div style="display:flex; gap:8px;">
                        <button onclick="loadRun(${run.id})" class="btn-primary" 
                            style="padding:4px 8px; font-size:0.75rem; background:#10b981; width:auto;">
                            Load
                        </button>
                        <button onclick="deleteRun(${run.id})" 
                            style="padding:4px 8px; font-size:0.75rem; border:1px solid #ef4444; color:#ef4444; background:white; border-radius:4px; cursor:pointer;">
                            Delete
                        </button>
                    </div>
                </div>
            `).join('');

        } catch (e) {
            console.error(e);
            container.innerHTML = '<div style="color: #ef4444; text-align: center;">Error loading runs</div>';
        }
    }

    async function loadRun(runId) {
        try {
            const res = await fetch(`/api/runs/${runId}`);
            const data = await res.json();

            if (data.result_json) {
                // Clear existing
                clearRouteLines();
                clearClusters();

                // RESTORE CONTEXT (Fix for Data Discrepancy)
                if (data.result_json.school) {
                    schoolMarker = L.marker([data.result_json.school.latitude, data.result_json.school.longitude], {
                        icon: L.divIcon({
                            className: 'school-icon',
                            html: '🏫',
                            iconSize: [40, 40],
                            iconAnchor: [20, 20]
                        })
                    })
                        .addTo(map)
                        .bindPopup(`<b>${data.result_json.school.name}</b><br>${data.result_json.school.address}`);
                }

                if (data.result_json.all_students) {
                    // Restore students list
                    // Use a temporary global variable or just re-render markers
                    const restoredStudents = data.result_json.all_students;

                    // Clear old markers
                    if (markers) {
                        Object.values(markers).forEach(m => map.removeLayer(m));
                    }
                    markers = {};

                    // Group students by coordinates
                    const groupedStudents = {};
                    restoredStudents.forEach(s => {
                        const key = `${s.latitude.toFixed(5)},${s.longitude.toFixed(5)}`;
                        if (!groupedStudents[key]) groupedStudents[key] = [];
                        groupedStudents[key].push(s);
                    });

                    // Re-plot students using the grouped logic
                    Object.values(groupedStudents).forEach(group => {
                        const count = group.length;
                        const s = group[0];
                        
                        let badgeHtml = '';
                        if (count > 1) {
                            badgeHtml = `<div style="position:absolute; top:-5px; right:-5px; background:#ef4444; color:white; border-radius:50%; width:16px; height:16px; font-size:10px; display:flex; align-items:center; justify-content:center; font-weight:bold; border:1px solid white; z-index:1000;">${count}</div>`;
                        }

                        const iconHtml = `<div class="custom-student-icon" style="position:relative;">
                            <i class="fas fa-user-graduate"></i>
                            ${badgeHtml}
                        </div>`;

                        const marker = L.marker([s.latitude, s.longitude], {
                            icon: L.divIcon({
                                className: 'student-marker-container',
                                html: iconHtml,
                                iconSize: [28, 28],
                                iconAnchor: [14, 14],
                                popupAnchor: [0, -14]
                            })
                        }).addTo(map);

                        // Build popup content
                        let popupContent = `<b>${s.address || 'Address'}</b><hr style="margin:4px 0; border:0; border-top:1px solid #ccc;">`;
                        popupContent += `<ul style="margin:0; padding-left:16px; font-size:0.9rem;">`;
                        group.forEach(st => {
                            popupContent += `<li>${st.name}</li>`;
                        });
                        popupContent += `</ul>`;

                        marker.bindPopup(popupContent);
                        
                        markers[s.id || s.name] = marker;
                        if (count > 1) {
                            group.forEach(st => {
                                markers[st.id || st.name] = marker;
                            });
                        }
                    });

                    if (document.getElementById('totalStudents')) {
                        document.getElementById('totalStudents').innerText = restoredStudents.length;
                    }
                }

                // Display new routes (This creates the DOM elements)
                displayRoutes(data.result_json);

                // Auto-switch to results
                switchTab('results');

                alert(`Loaded: ${data.name}`);
            }
        } catch (e) {
            console.error(e);
            alert('Error loading run details: ' + (e.message || e));
        }
    }

    async function deleteRun(runId) {
        if (!confirm('Delete this saved run?')) return;

        try {
            await fetch(`/api/runs/${runId}`, { method: 'DELETE' });
            loadSavedRuns(); // Refresh
        } catch (e) {
            console.error(e);
            alert('Error deleting run');
        }
    }

    // --- Tab Switching Logic ---
    function switchTab(tabName) {
        const headerTitle = document.getElementById('headerTitle');
        if (headerTitle) headerTitle.innerText = tabName === 'setup' ? 'Setup Configuration' : 'Manage routes';
        
        const btnSetup = document.getElementById('tab-btn-setup');
        const btnResults = document.getElementById('tab-btn-results');
        if (btnSetup && btnResults) {
            if (tabName === 'setup') {
                btnSetup.className = "h-7 px-3 text-xs font-semibold rounded-md transition-colors flex items-center gap-1.5 bg-blue-50 text-blue-700";
                btnResults.className = "h-7 px-3 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5 text-slate-600 hover:bg-slate-100";
            } else {
                btnResults.className = "h-7 px-3 text-xs font-semibold rounded-md transition-colors flex items-center gap-1.5 bg-blue-50 text-blue-700";
                btnSetup.className = "h-7 px-3 text-xs font-medium rounded-md transition-colors flex items-center gap-1.5 text-slate-600 hover:bg-slate-100";
            }
        }
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.add('hidden');
            content.classList.remove('flex');
        });
        const activeContent = document.getElementById(`tab-${tabName}`);
        if (activeContent) {
            activeContent.classList.remove('hidden');
            activeContent.classList.add('flex');
        }
        if (typeof map !== 'undefined' && map) {
            setTimeout(() => { map.invalidateSize(); }, 200);
        }
        if(typeof lucide !== 'undefined') lucide.createIcons();
    }

    // Initialize (Load Students on start, verify tab)
    window.addEventListener('DOMContentLoaded', () => {
        const savedRoutesData = sessionStorage.getItem('optimizedRoutesFullData');
        if (savedRoutesData) {
            try {
                const data = JSON.parse(savedRoutesData);
                if (data && data.routes && data.routes.length > 0) {
                    setTimeout(() => {
                        displayRoutes(data);
                        switchTab('results');
                    }, 200); // slight delay to ensure map/markers are ready
                    initChat();
                    return;
                }
            } catch (e) {
                console.error('Error restoring routes from sessionStorage', e);
            }
        }

        // Ensure Setup tab is active if no saved data
        switchTab('setup');
        initChat();
    });

    // ============================================================
    // AI CHAT — Gemini-powered route editor
    // ============================================================
    const CHAT_HISTORY_KEY = 'chatHistory_v1';
    const CHAT_MODEL_KEY = 'chatModel_v1';
    const CHAT_MAX_HISTORY = 10;       // turns sent to backend
    const CHAT_UNDO_DEPTH = 10;        // snapshots kept

    let chatHistory = [];              // [{role:'user'|'assistant', text:'...'}]
    let chatUndoStack = [];            // snapshots of optimizedRoutesData
    let chatBusy = false;
    let chatModel = 'gemini-2.5-flash';

    function initChat() {
        chatModel = localStorage.getItem(CHAT_MODEL_KEY) || 'gemini-2.5-flash';
        document.querySelectorAll('#chatModelToggle button').forEach(b => {
            b.classList.toggle('active', b.dataset.model === chatModel);
        });
        try {
            const stored = sessionStorage.getItem(CHAT_HISTORY_KEY);
            chatHistory = stored ? JSON.parse(stored) : [];
        } catch (_) { chatHistory = []; }
        renderChatBody();
    }

    function openChat() {
        document.getElementById('chatPanel').classList.add('open');
        document.getElementById('chatFab').classList.add('hidden');
        updateChatAvailability();
        setTimeout(() => {
            document.getElementById('chatInput').focus();
            scrollChatToBottom();
        }, 50);
    }

    function closeChat() {
        document.getElementById('chatPanel').classList.remove('open');
        document.getElementById('chatFab').classList.remove('hidden');
    }

    function setChatModel(modelName) {
        chatModel = modelName;
        localStorage.setItem(CHAT_MODEL_KEY, modelName);
        document.querySelectorAll('#chatModelToggle button').forEach(b => {
            b.classList.toggle('active', b.dataset.model === modelName);
        });
    }

    function updateChatAvailability() {
        const ready = optimizedRoutesData && optimizedRoutesData.routes && optimizedRoutesData.routes.length > 0;
        document.getElementById('chatDisabledOverlay').style.display = ready ? 'none' : 'flex';
        document.getElementById('chatInput').disabled = !ready;
        document.getElementById('chatSendBtn').disabled = !ready;
    }

    function autoResizeChatInput(el) {
        el.style.height = 'auto';
        el.style.height = Math.min(120, el.scrollHeight) + 'px';
    }

    function handleChatKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    }

    function pushChatTurn(role, text, extras) {
        const turn = { role, text };
        if (extras) Object.assign(turn, extras);
        chatHistory.push(turn);
        if (chatHistory.length > CHAT_MAX_HISTORY * 2) {
            chatHistory.splice(0, chatHistory.length - CHAT_MAX_HISTORY * 2);
        }
        sessionStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(chatHistory));
        renderChatBody();
    }

    function renderChatBody() {
        const body = document.getElementById('chatBody');
        if (!body) return;
        body.innerHTML = '';

        if (chatHistory.length === 0) {
            body.innerHTML = `
                <div class="chat-bubble assistant">
                    Natural-language route editor. Describe changes and I'll apply them.
                    <div class="chat-suggestions">
                        <span class="chat-suggestion" onclick="insertSuggestion(this)">move student S001 to bus 3</span>
                        <span class="chat-suggestion" onclick="insertSuggestion(this)">swap A and B</span>
                        <span class="chat-suggestion" onclick="insertSuggestion(this)">merge bus 2 into bus 5</span>
                        <span class="chat-suggestion" onclick="insertSuggestion(this)">move 3 students from bus 4 to bus 6</span>
                    </div>
                </div>`;
            return;
        }

        chatHistory.forEach(turn => {
            const div = document.createElement('div');
            div.className = `chat-bubble ${turn.role}`;
            div.textContent = turn.text || '';

            if (turn.toolCalls && turn.toolCalls.length) {
                const wrap = document.createElement('div');
                wrap.className = 'chat-toolcalls';
                turn.toolCalls.forEach(tc => {
                    const ok = tc.result && tc.result.ok;
                    const row = document.createElement('div');
                    row.className = 'chat-toolcall ' + (ok ? 'ok' : 'fail');
                    const status = ok ? '<i data-lucide="check" class="w-3.5 h-3.5"></i>' : '<i data-lucide="x" class="w-3.5 h-3.5"></i>';
                    const summary = ok ? (tc.result.summary || '') : (tc.result && tc.result.error || 'failed');
                    row.innerHTML = `<span class="tc-status">${status}</span><span><span class="tc-name">${tc.name}</span> — ${escapeHtml(summary)}</span>`;
                    setTimeout(() => { lucide.createIcons(); }, 10);
                    wrap.appendChild(row);
                });
                div.appendChild(wrap);
            }

            if (turn.warnings && turn.warnings.length) {
                const wrap = document.createElement('div');
                wrap.className = 'chat-warnings';
                wrap.innerHTML = '<strong>Warnings</strong><ul>' +
                    turn.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('') + '</ul>';
                div.appendChild(wrap);
            }

            body.appendChild(div);
        });

        scrollChatToBottom();
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[c]));
    }

    function scrollChatToBottom() {
        const body = document.getElementById('chatBody');
        if (body) body.scrollTop = body.scrollHeight;
    }

    function insertSuggestion(el) {
        const input = document.getElementById('chatInput');
        input.value = el.textContent.trim();
        input.focus();
        autoResizeChatInput(input);
    }

    function showTypingIndicator(show) {
        const body = document.getElementById('chatBody');
        let typing = document.getElementById('chatTyping');
        if (show) {
            if (!typing) {
                typing = document.createElement('div');
                typing.id = 'chatTyping';
                typing.className = 'chat-typing';
                typing.innerHTML = '<span></span><span></span><span></span>';
                body.appendChild(typing);
                scrollChatToBottom();
            }
        } else if (typing) {
            typing.remove();
        }
    }

    async function sendChatMessage() {
        if (chatBusy) return;
        const input = document.getElementById('chatInput');
        const message = input.value.trim();
        if (!message) return;

        if (!optimizedRoutesData || !optimizedRoutesData.routes || optimizedRoutesData.routes.length === 0) {
            pushChatTurn('assistant', 'No active route set. Run an optimisation first.');
            return;
        }

        chatBusy = true;
        document.getElementById('chatSendBtn').disabled = true;
        input.value = '';
        autoResizeChatInput(input);

        pushChatTurn('user', message);
        showTypingIndicator(true);

        // Snapshot for undo BEFORE we mutate anything
        const snapshot = JSON.parse(JSON.stringify(optimizedRoutesData));

        // History sent to backend: drop the just-pushed user turn, take last N pairs
        const sendHistory = chatHistory.slice(0, -1).slice(-CHAT_MAX_HISTORY * 2);

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message,
                    routes: optimizedRoutesData.routes,
                    history: sendHistory,
                    model: chatModel,
                    school_time: document.getElementById('schoolTime')?.value || '07:30',
                    max_ride_time: document.getElementById('maxRideTime')?.value || 60
                })
            });
            const data = await res.json();
            showTypingIndicator(false);

            if (!res.ok || data.error) {
                pushChatTurn('assistant', 'Error: ' + (data.error || res.statusText));
                return;
            }

            const applied = (data.tool_calls || []).some(tc => tc.result && tc.result.ok);
            if (applied) {
                chatUndoStack.push(snapshot);
                if (chatUndoStack.length > CHAT_UNDO_DEPTH) chatUndoStack.shift();
                document.getElementById('chatUndoBtn').disabled = false;

                optimizedRoutesData.routes = data.routes;
                displayRoutes(optimizedRoutesData);
                pulseChangedBuses(data.tool_calls);
            }

            pushChatTurn('assistant', data.ai_message || '(no response)', {
                toolCalls: data.tool_calls || [],
                warnings: data.warnings || []
            });
        } catch (e) {
            showTypingIndicator(false);
            pushChatTurn('assistant', 'Network error: ' + e.message);
        } finally {
            chatBusy = false;
            updateChatAvailability();
        }
    }

    function pulseChangedBuses(toolCalls) {
        const affected = new Set();
        (toolCalls || []).forEach(tc => {
            const a = tc.args || {};
            if (typeof a.to_bus === 'number') affected.add(a.to_bus - 1);
            if (typeof a.from_bus === 'number') affected.add(a.from_bus - 1);
            if (typeof a.bus_number === 'number') affected.add(a.bus_number - 1);
        });
        affected.forEach(idx => {
            const el = document.getElementById(`route-accordion-${idx}`);
            if (!el) return;
            el.style.transition = 'box-shadow 0.4s ease, background 0.4s ease';
            const prevBg = el.style.background;
            el.style.background = 'rgba(56, 189, 248, 0.12)';
            el.style.boxShadow = '0 0 0 2px rgba(56, 189, 248, 0.4)';
            setTimeout(() => {
                el.style.background = prevBg;
                el.style.boxShadow = '';
            }, 1200);
        });
    }

    function undoChatAction() {
        if (chatUndoStack.length === 0) return;
        const prev = chatUndoStack.pop();
        optimizedRoutesData = prev;
        currentRoutes = prev.routes;
        sessionStorage.setItem('latestRoutes', JSON.stringify(prev.routes));
        sessionStorage.setItem('optimizedRoutesFullData', JSON.stringify(prev));
        displayRoutes(prev);
        pushChatTurn('assistant', 'Reverted last change.');
        document.getElementById('chatUndoBtn').disabled = chatUndoStack.length === 0;
    }

    function clearChatHistory() {
        if (!confirm('Clear conversation history? Undo stack will also be reset.')) return;
        chatHistory = [];
        chatUndoStack = [];
        sessionStorage.removeItem(CHAT_HISTORY_KEY);
        document.getElementById('chatUndoBtn').disabled = true;
        renderChatBody();
    }

    // Re-check chat availability whenever routes change
    const _origDisplayRoutes = displayRoutes;
    displayRoutes = function(data) {
        _origDisplayRoutes(data);
        updateChatAvailability();
    };


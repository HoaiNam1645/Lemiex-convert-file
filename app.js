// PES Design Information Viewer - Main Application
class PESViewer {
    constructor() {
        this.currentPESData = null;
        this.needleAssignment = new Array(12).fill(null); // 12 needles (index 0-11 for needles 1-12)
        this.colorData = [];
        this.draggedNeedle = null; // Changed from draggedColor to draggedNeedle
        this.currentHash = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.initializeNeedles();
        this.showStatus('Ready. Please load a JSON file to view design data.', 'info');
        
        // Auto load sample data for testing
        setTimeout(() => {
            this.loadJSONData();
        }, 1000);
    }

    setupEventListeners() {
        const loadFileBtn = document.getElementById('loadFileBtn');
        const pesFileInput = document.getElementById('pesFileInput');

        loadFileBtn.addEventListener('click', () => {
            pesFileInput.click();
        });

        pesFileInput.addEventListener('change', (event) => {
            const file = event.target.files[0];
            if (file && file.name.toLowerCase().endsWith('.json')) {
                this.loadJSONFile(file);
            } else {
                this.showStatus('Please select a JSON file', 'error');
            }
        });

        // Setup drag and drop for the whole document
        document.addEventListener('dragover', (e) => e.preventDefault());
        document.addEventListener('drop', (e) => e.preventDefault());
    }

    initializeNeedles() {
        const needleContainer = document.querySelector('.needle-container');
        needleContainer.innerHTML = '';

        for (let i = 0; i < 12; i++) {
            const needlePosition = document.createElement('div');
            needlePosition.className = 'needle-position';
            needlePosition.innerHTML = `
                <div class="needle-code" id="needleCode${i + 1}"></div>
                <div class="needle-box" data-needle="${i + 1}" id="needleBox${i + 1}">
                    ${i + 1}
                </div>
            `;
            
            const needleBox = needlePosition.querySelector('.needle-box');
            this.setupNeedleDragSource(needleBox, i); // Changed to drag source instead of drop target
            
            needleContainer.appendChild(needlePosition);
        }
    }

    setupNeedleDragSource(needleBox, needleIndex) {
        // Touch/Mobile drag support
        let touchStartPos = null;
        let isDragging = false;
        
        // Touch events for mobile
        needleBox.addEventListener('touchstart', (e) => {
            const needleData = this.needleAssignment[needleIndex];
            if (needleData) {
                touchStartPos = {
                    x: e.touches[0].clientX,
                    y: e.touches[0].clientY
                };
                needleBox.style.transition = 'none';
                // Add touch feedback
                needleBox.classList.add('touch-active');
                setTimeout(() => needleBox.classList.remove('touch-active'), 150);
                e.preventDefault(); // Prevent scrolling
            }
        }, { passive: false });

        needleBox.addEventListener('touchmove', (e) => {
            const needleData = this.needleAssignment[needleIndex];
            if (needleData && touchStartPos) {
                const currentTouch = e.touches[0];
                const deltaX = currentTouch.clientX - touchStartPos.x;
                const deltaY = currentTouch.clientY - touchStartPos.y;
                
                // Start dragging if moved enough (lower threshold for mobile)
                if (!isDragging && (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3)) {
                    isDragging = true;
                    this.draggedNeedle = {
                        needleIndex: needleIndex,
                        needleNumber: needleIndex + 1,
                        data: needleData
                    };
                    needleBox.classList.add('dragging');
                    this.createNeedleDragPreview(needleData, needleIndex + 1);
                }
                
                if (isDragging) {
                    // Move the needle box with finger
                    needleBox.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
                    needleBox.style.zIndex = '1000';
                    
                    // Temporarily hide the dragging element to get element below
                    needleBox.style.visibility = 'hidden';
                    const elementBelow = document.elementFromPoint(currentTouch.clientX, currentTouch.clientY);
                    needleBox.style.visibility = 'visible';
                    
                    this.handleTouchDragOver(elementBelow);
                }
                e.preventDefault();
            }
        }, { passive: false });

        needleBox.addEventListener('touchend', (e) => {
            if (isDragging) {
                const needleData = this.needleAssignment[needleIndex];
                if (needleData) {
                    const touch = e.changedTouches[0];
                    
                    // Temporarily hide the dragging element to get element below
                    needleBox.style.visibility = 'hidden';
                    const elementBelow = document.elementFromPoint(touch.clientX, touch.clientY);
                    needleBox.style.visibility = 'visible';
                    
                    console.log('Touch drop - Element below:', elementBelow);
                    console.log('Touch coordinates:', touch.clientX, touch.clientY);
                    
                    this.handleTouchDrop(elementBelow, touch.clientX, touch.clientY);
                }
                
                // Reset styles
                needleBox.style.transform = '';
                needleBox.style.zIndex = '';
                needleBox.style.transition = '';
                needleBox.classList.remove('dragging');
                this.draggedNeedle = null;
                this.removeDragPreview();
                isDragging = false;
            }
            touchStartPos = null;
        });

        // Desktop drag events
        needleBox.addEventListener('dragstart', (e) => {
            const needleData = this.needleAssignment[needleIndex];
            if (needleData) {
                this.draggedNeedle = {
                    needleIndex: needleIndex,
                    needleNumber: needleIndex + 1,
                    data: needleData
                };
                needleBox.classList.add('dragging');
                this.createNeedleDragPreview(needleData, needleIndex + 1);
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', '');
            } else {
                e.preventDefault(); // Prevent drag if no color assigned
            }
        });

        needleBox.addEventListener('dragend', (e) => {
            needleBox.classList.remove('dragging');
            this.draggedNeedle = null;
            this.removeDragPreview();
        });

        // Setup drop target for needles (to receive other needles)
        this.setupNeedleDropTarget(needleBox, needleIndex);

        // Update draggable attribute based on assignment
        this.updateNeedleDraggable(needleBox, needleIndex);
    }

    setupNeedleDropTarget(needleBox, needleIndex) {
        needleBox.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (this.draggedNeedle && this.draggedNeedle.needleIndex !== needleIndex) {
                needleBox.classList.add('drop-target');
            }
        });

        needleBox.addEventListener('dragleave', (e) => {
            if (!needleBox.contains(e.relatedTarget)) {
                needleBox.classList.remove('drop-target');
            }
        });

        needleBox.addEventListener('drop', (e) => {
            e.preventDefault();
            needleBox.classList.remove('drop-target');
            
            if (this.draggedNeedle && this.draggedNeedle.needleIndex !== needleIndex) {
                this.swapNeedles(this.draggedNeedle.needleIndex, needleIndex);
                this.draggedNeedle = null;
                this.removeDragPreview();
            }
        });
    }

    swapNeedles(fromIndex, toIndex) {
        const fromNeedle = this.needleAssignment[fromIndex];
        const toNeedle = this.needleAssignment[toIndex];
        
        // Move needle from 'fromIndex' to 'toIndex'
        this.needleAssignment[toIndex] = fromNeedle;
        this.needleAssignment[fromIndex] = toNeedle; // This could be null if target was empty
        
        // Update needle numbers in color data for both positions
        this.colorData.forEach(color => {
            // Update color at new position (toIndex)
            if (fromNeedle && color.code === fromNeedle.code) {
                color.needle_number = toIndex + 1;
            }
            // Update color at original position (fromIndex) - could be null now
            if (toNeedle && color.code === toNeedle.code) {
                color.needle_number = fromIndex + 1;
            } else if (!toNeedle && fromNeedle && color.code === fromNeedle.code) {
                // If we moved to an empty spot, make sure we don't have duplicate assignments
                // This is already handled above, but kept for clarity
            }
        });

        // Update displays
        this.updateNeedleDisplay();
        this.updateColorTable();
        this.saveAssignmentCache();
        
        const fromDesc = fromNeedle ? `${fromNeedle.code}` : 'empty';
        const toDesc = toNeedle ? `${toNeedle.code}` : 'empty';
        
        if (!toNeedle) {
            this.showStatus(`Moved Needle ${fromIndex + 1} (${fromDesc}) to position ${toIndex + 1}`, 'success');
        } else {
            this.showStatus(`Swapped Needle ${fromIndex + 1} (${fromDesc}) with Needle ${toIndex + 1} (${toDesc})`, 'success');
        }
    }

    loadAssignmentCache() {
        if (!this.currentHash) return;
        try {
            const cached = localStorage.getItem(`needle_assignment_${this.currentHash}`);
            if (!cached) return;
            const data = JSON.parse(cached);
            if (data.assignments) {
                this.needleAssignment = data.assignments;
            }
            if (Array.isArray(data.colors)) {
                const map = new Map();
                data.colors.forEach(c => map.set(c.sequence, c.needle_number));
                this.colorData = this.colorData.map(c => ({ ...c, needle_number: map.get(c.sequence) ?? c.needle_number }));
            }
            this.showStatus(`Loaded cached needles for ${this.currentPESData.filename}`, 'info');
        } catch (err) {
            console.error('Failed to load assignment cache', err);
        }
    }

    saveAssignmentCache() {
        if (!this.currentHash) return;
        try {
            const payload = {
                assignments: this.needleAssignment,
                colors: this.colorData.map(c => ({ sequence: c.sequence, needle_number: c.needle_number }))
            };
            localStorage.setItem(`needle_assignment_${this.currentHash}`, JSON.stringify(payload));
        } catch (err) {
            console.error('Failed to save assignment cache', err);
        }
    }

    // Touch drag helper methods
    handleTouchDragOver(element) {
        // Remove previous drop target highlights
        document.querySelectorAll('.needle-box.drop-target').forEach(box => {
            box.classList.remove('drop-target');
        });
        
        // Find needle box (could be the element itself or a parent)
        let needleBox = element;
        while (needleBox && !needleBox.classList.contains('needle-box')) {
            needleBox = needleBox.parentElement;
        }
        
        // Add drop target highlight if hovering over a different needle
        if (needleBox && needleBox.classList.contains('needle-box') && this.draggedNeedle) {
            const targetNeedle = parseInt(needleBox.getAttribute('data-needle')) - 1;
            if (targetNeedle !== this.draggedNeedle.needleIndex) {
                needleBox.classList.add('drop-target');
            }
        }
    }

    handleTouchDrop(element, touchX, touchY) {
        console.log('handleTouchDrop called with element:', element);
        console.log('element classes:', element ? element.className : 'null element');
        console.log('draggedNeedle:', this.draggedNeedle);
        

        
        // Remove all drop target highlights
        document.querySelectorAll('.needle-box.drop-target').forEach(box => {
            box.classList.remove('drop-target');
        });
        
        // Find needle box (could be the element itself or a parent)
        let needleBox = element;
        while (needleBox && !needleBox.classList.contains('needle-box') && needleBox !== document.body) {
            needleBox = needleBox.parentElement;
        }
        
        // If not found by traversing up, try to find by coordinates
        if (!needleBox || !needleBox.classList.contains('needle-box')) {
            if (touchX && touchY) {
                const needleBoxes = document.querySelectorAll('.needle-box');
                needleBoxes.forEach(box => {
                    const rect = box.getBoundingClientRect();
                    if (touchX >= rect.left && touchX <= rect.right && 
                        touchY >= rect.top && touchY <= rect.bottom) {
                        needleBox = box;
                    }
                });
            }
        }
        
        // Handle drop if on a needle box
        if (needleBox && needleBox.classList.contains('needle-box') && this.draggedNeedle) {
            const targetNeedle = parseInt(needleBox.getAttribute('data-needle')) - 1;
            console.log('Target needle index:', targetNeedle);
            console.log('Source needle index:', this.draggedNeedle.needleIndex);
            
            if (targetNeedle !== this.draggedNeedle.needleIndex && !isNaN(targetNeedle)) {
                console.log('Calling swapNeedles');
                this.showStatus(`Touch swap: ${this.draggedNeedle.needleIndex + 1} → ${targetNeedle + 1}`, 'success');
                this.swapNeedles(this.draggedNeedle.needleIndex, targetNeedle);
            } else {
                console.log('Same needle or invalid target - no swap needed');
                this.showStatus(`Touch drop on same needle (${targetNeedle + 1})`, 'info');
            }
        } else {
            console.log('Drop conditions not met:', {
                hasElement: !!element,
                foundNeedleBox: !!needleBox,
                isNeedleBox: needleBox ? needleBox.classList.contains('needle-box') : false,
                hasDraggedNeedle: !!this.draggedNeedle
            });
            
            if (!needleBox) {
                this.showStatus('Touch dropped on empty area', 'info');
            } else if (!this.draggedNeedle) {
                this.showStatus('No needle being dragged', 'info');
            }
        }
    }

    async loadJSONData() {
        try {
            this.showStatus('Loading PES data...', 'info');
            const response = await fetch('ZOEYver2.json');
            if (!response.ok) {
                throw new Error('Failed to load sample data');
            }
            const jsonData = await response.json();
            this.processPESData(jsonData);
            this.showStatus('PES data loaded successfully', 'success');
        } catch (error) {
            console.error('Error loading JSON data:', error);
            this.showStatus('Failed to load PES data. Please use "Load JSON Data" button to select a file.', 'error');
        }
    }

    async loadJSONFile(file) {
        try {
            this.showStatus('Loading JSON file...', 'info');
            const text = await file.text();
            const jsonData = JSON.parse(text);
            this.processPESData(jsonData);
            this.showStatus(`Loaded ${file.name}`, 'success');
        } catch (error) {
            console.error('Error loading JSON file:', error);
            this.showStatus('Invalid JSON file format', 'error');
        }
    }

    processPESData(jsonData) {
        // Store the complete JSON data
        this.currentPESData = {
            filename: jsonData.file_info.filename,
            stitches: jsonData.file_info.stitch_count,
            height: jsonData.file_info.height_mm,
            width: jsonData.file_info.width_mm,
            colors: jsonData.file_info.color_count,
            stops: jsonData.file_info.stops,
            preview: jsonData.preview,
            hash8: jsonData.file_info.hash8 || null
        };
        this.currentHash = jsonData.file_info.hash8 || null;

        // Convert colors data to the format expected by the interface
        this.colorData = jsonData.colors.map(color => ({
            id: color.id,
            sequence: color.sequence,
            code: color.code,
            name: color.name,
            chart: color.chart,
            rgb: color.rgb_hex,
            needle_number: color.needle_number,
            stitch_count: color.stitch_count
        }));

        // Load needle assignments from JSON
        this.needleAssignment.fill(null);
        if (jsonData.needle_assignment && jsonData.needle_assignment.assignments) {
            Object.entries(jsonData.needle_assignment.assignments).forEach(([needleNum, assignment]) => {
                if (assignment && assignment !== null) {
                    const needleIndex = parseInt(needleNum) - 1;
                    if (needleIndex >= 0 && needleIndex < 12) {
                        this.needleAssignment[needleIndex] = {
                            code: assignment.code,
                            name: assignment.name,
                            rgb: assignment.rgb_hex
                        };
                        
                        // Update corresponding colors with needle numbers
                        this.colorData.forEach(color => {
                            if (color.code === assignment.code) {
                                color.needle_number = parseInt(needleNum);
                            }
                        });
                        
                        console.log(`Loaded needle ${needleNum}: ${assignment.code} - ${assignment.name}`);
                    }
                }
            });
        } else {
            // If no needle assignments in JSON, try to load from color data
            this.colorData.forEach(color => {
                if (color.needle_number) {
                    const needleIndex = color.needle_number - 1;
                    if (needleIndex >= 0 && needleIndex < 12) {
                        this.needleAssignment[needleIndex] = {
                            code: color.code,
                            name: color.name,
                            rgb: color.rgb
                        };
                        console.log(`Loaded from color data - needle ${color.needle_number}: ${color.code}`);
                    }
                }
            });
        }

        // Load cached assignments based on hash8 (localStorage)
        this.loadAssignmentCache();

        // Persist current state to cache
        this.saveAssignmentCache();

        this.updateUI();
    }

    updateNeedleDraggable(needleBox, needleIndex) {
        const hasAssignment = this.needleAssignment[needleIndex] !== null;
        needleBox.draggable = hasAssignment;
        needleBox.style.cursor = hasAssignment ? 'grab' : 'pointer';
    }

    createNeedleDragPreview(needleData, needleNumber) {
        this.removeDragPreview();
        
        const preview = document.createElement('div');
        preview.className = 'drag-preview needle-preview';
        preview.id = 'dragPreview';
        preview.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px;">
                <div class="needle-mini" style="width: 20px; height: 15px; background-color: ${needleData.rgb}; border: 1px solid #333; border-radius: 2px; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; color: ${this.getContrastColor(needleData.rgb)}">${needleNumber}</div>
                <span>Needle ${needleNumber}: ${needleData.code} - ${needleData.name}</span>
            </div>
        `;
        
        document.body.appendChild(preview);
    }

    getContrastColor(hexColor) {
        const rgb = this.hexToRgb(hexColor);
        const brightness = (rgb.r * 299 + rgb.g * 587 + rgb.b * 114) / 1000;
        return brightness > 128 ? '#000' : '#fff';
    }

    updateUI() {
        // Update file information
        document.getElementById('fileName').textContent = this.currentPESData.filename;
        document.getElementById('stitchCount').textContent = this.currentPESData.stitches.toLocaleString();
        document.getElementById('designHeight').textContent = `${this.currentPESData.height} mm`;
        document.getElementById('designWidth').textContent = `${this.currentPESData.width} mm`;
        document.getElementById('colorCount').textContent = this.currentPESData.colors;
        const stopsEl = document.getElementById('stopsCount');
        if (stopsEl) stopsEl.textContent = this.currentPESData.stops;

        // Update design preview
        this.updateDesignPreview();

        // Update color table
        this.updateColorTable();
        
        // Update needle display
        this.updateNeedleDisplay();
    }

    updateDesignPreview() {
        const previewImg = document.getElementById('designPreview');
        const previewPlaceholder = document.getElementById('previewPlaceholder');
        
        if (this.currentPESData && this.currentPESData.preview && 
            this.currentPESData.preview.image_data && 
            this.currentPESData.preview.encoding === 'base64') {
            
            // Create data URL for base64 image
            const mimeType = this.currentPESData.preview.format === 'png' ? 'image/png' : 
                            this.currentPESData.preview.format === 'jpg' || this.currentPESData.preview.format === 'jpeg' ? 'image/jpeg' : 
                            'image/png'; // Default to PNG
            
            const dataUrl = `data:${mimeType};base64,${this.currentPESData.preview.image_data}`;
            
            // Set image source and show preview
            previewImg.src = dataUrl;
            previewImg.style.display = 'block';
            previewPlaceholder.style.display = 'none';
        } else {
            // No preview available, show placeholder
            previewImg.style.display = 'none';
            previewPlaceholder.style.display = 'block';
        }
    }

    updateColorTable() {
        const tbody = document.getElementById('colorTableBody');
        tbody.innerHTML = '';

        this.colorData.forEach((color, index) => {
            const row = document.createElement('tr');
            row.dataset.colorId = color.id;

            const needleNumber = this.getNeedleNumberForColor(color);
            const needleDisplay = needleNumber ? needleNumber : '';

            row.innerHTML = `
                <td>${color.sequence}</td>
                <td class="needle-number">${needleDisplay}</td>
                <td><div class="color-swatch" style="background-color: ${color.rgb}"></div></td>
                <td>${color.code}</td>
                <td>${color.name}</td>
                <td>${color.chart}</td>
            `;

            // No drop functionality needed for color rows anymore
            
            tbody.appendChild(row);
        });
    }





    updateDragPreviewPosition = (e) => {
        const preview = document.getElementById('dragPreview');
        if (preview) {
            preview.style.left = e.clientX + 'px';
            preview.style.top = e.clientY + 'px';
        }
    }

    removeDragPreview() {
        const preview = document.getElementById('dragPreview');
        if (preview) {
            preview.remove();
        }
        document.removeEventListener('mousemove', this.updateDragPreviewPosition);
    }

    addNeedleAssignmentFromJSON(needleIndex, needleData) {
        // Helper method to add needle assignment from JSON data
        this.needleAssignment[needleIndex] = needleData;
        
        // Update corresponding colors with needle numbers
        this.colorData.forEach(color => {
            if (color.code === needleData.code) {
                color.needle_number = needleIndex + 1;
            }
        });
    }

    updateNeedleDisplay() {
        for (let i = 0; i < 12; i++) {
            const needleBox = document.getElementById(`needleBox${i + 1}`);
            const needleCode = document.getElementById(`needleCode${i + 1}`);
            const needleData = this.needleAssignment[i];

            if (needleData) {
                needleBox.style.backgroundColor = needleData.rgb;
                needleBox.classList.add('occupied');
                needleCode.textContent = needleData.code;
                
                // Calculate text color based on background brightness
                const rgb = this.hexToRgb(needleData.rgb);
                const brightness = (rgb.r * 299 + rgb.g * 587 + rgb.b * 114) / 1000;
                needleBox.style.color = brightness > 128 ? '#000' : '#fff';
            } else {
                needleBox.style.backgroundColor = '#ecf0f1';
                needleBox.style.color = '#2c3e50';
                needleBox.classList.remove('occupied');
                needleCode.textContent = '';
            }
            
            // Update draggable status
            this.updateNeedleDraggable(needleBox, i);
        }
    }

    getNeedleNumberForColor(color) {
        return color.needle_number || '';
    }

    hexToRgb(hex) {
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 0, g: 0, b: 0 };
    }

    showStatus(message, type = 'info') {
        const statusEl = document.getElementById('statusMessage');
        statusEl.textContent = message;
        statusEl.className = `status-message ${type} show`;
        
        setTimeout(() => {
            statusEl.classList.remove('show');
        }, 3000);
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new PESViewer();
});
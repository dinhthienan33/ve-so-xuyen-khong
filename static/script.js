// ================================================================
    // CONFIG
    // ================================================================
    const TIER_CONFIG = {
        '0': { badge: 'ĐB', css: 'tier-db', label: 'Giải Đặc Biệt' },
        '1': { badge: 'G1', css: 'tier-1',  label: 'Giải Nhất' },
        '2': { badge: 'G2', css: 'tier-2',  label: 'Giải Nhì' },
        '3': { badge: 'G3', css: 'tier-3',  label: 'Giải Ba' },
        '4': { badge: 'G4', css: 'tier-4',  label: 'Giải Tư' },
        '5': { badge: 'G5', css: 'tier-5',  label: 'Giải Năm' },
        '6': { badge: 'G6', css: 'tier-6',  label: 'Giải Sáu' },
        '7': { badge: 'G7', css: 'tier-7',  label: 'Giải Bảy' },
        '8': { badge: 'G8', css: 'tier-8',  label: 'Giải Tám' },
        'phu_db':       { badge: 'PHỤ', css: 'tier-phu', label: 'Giải Phụ Đặc Biệt' },
        'khuyen_khich': { badge: 'KK',  css: 'tier-kk',  label: 'Giải Khuyến Khích' },
    };

    // ================================================================
    // HELPERS
    // ================================================================
    function formatMoney(amount) {
        if (amount >= 1_000_000_000) return (amount / 1_000_000_000).toFixed(1) + ' tỷ';
        if (amount >= 1_000_000)     return (amount / 1_000_000).toFixed(0) + ' triệu';
        if (amount >= 1_000)         return (amount / 1_000).toFixed(0) + ' nghìn';
        return amount.toLocaleString('vi-VN');
    }

    function formatDate(dateStr) {
        const [y, m, d] = dateStr.split('-');
        return `${d}/${m}/${y}`;
    }

    function formatDaysAgo(days) {
        if (days === 0) return 'hôm nay';
        if (days < 30) return `${days} ngày trước`;
        const months = Math.floor(days / 30);
        if (months < 12) return `${months} tháng trước`;
        const years = Math.floor(days / 365);
        const remainMonths = Math.floor((days % 365) / 30);
        return `${years} năm ${remainMonths} tháng trước`;
    }

    function highlightNumber(number, suffix, digitsMatched) {
        if (number.length <= digitsMatched) {
            return `<span class="matched">${number}</span>`;
        }
        const unmatchedPart = number.slice(0, number.length - digitsMatched);
        const matchedPart = number.slice(-digitsMatched);
        return `<span class="unmatched">${unmatchedPart}</span><span class="matched">${matchedPart}</span>`;
    }

    function buildDescription(suffix, digitsMatched, prizeTier) {
        if (prizeTier === 'phu_db') return '5 số cuối giống ĐB, số đầu khác';
        if (prizeTier === 'khuyen_khich') return 'Sai đúng 1 chữ số so với ĐB';
        if (digitsMatched === 6) return `Khớp toàn bộ 6 chữ số`;
        return `Khớp ${digitsMatched} chữ số cuối [${suffix}]`;
    }

    // ================================================================
    // RENDER
    // ================================================================
    function renderResults(data) {
        const container = document.getElementById('prizeTierListContainer');
        container.innerHTML = '';

        // Stats bar
        document.getElementById('statTotalMatch').textContent = data.total_matches;
        document.getElementById('statBestPrize').textContent = data.best_prize_name || '—';
        document.getElementById('statBestValue').textContent = data.best_prize_value > 0
            ? formatMoney(data.best_prize_value) + ' đồng'
            : '—';

        // Summary
        document.getElementById('summaryNumber').textContent = data.ticket_number;
        document.getElementById('summaryDesc').innerHTML = data.total_matches > 0
            ? `Số này đã trúng <span class="highlight">${data.total_matches} lần</span> trong lịch sử xổ số`
            : 'Số này chưa từng xuất hiện ở bất kỳ giải nào trong dữ liệu đã crawl';

        // Jackpot alert
        const jackpot = document.getElementById('jackpotAlert');
        const dbTier = data.tiers.find(t => t.prize_tier === '0');
        if (dbTier && dbTier.match_count > 0) {
            const first = dbTier.matches[0];
            jackpot.innerHTML = `
                <h2>🏆 TRỜI ƠI! TRÚNG GIẢI ĐẶC BIỆT!</h2>
                <p>Số <strong>${first.number}</strong> đã từng trúng Giải Đặc Biệt</p>
                <span class="prize-amount">2.000.000.000 VNĐ</span>
                <p>tại <strong>${first.province}</strong> ngày <strong>${formatDate(first.draw_date)}</strong></p>
            `;
            jackpot.classList.add('visible');
        } else {
            jackpot.classList.remove('visible');
        }

        // Render each prize tier
        for (const tier of data.tiers) {
            const config = TIER_CONFIG[tier.prize_tier] || { badge: '?', css: '', label: tier.prize_name };
            const hasMatch = tier.match_count > 0;
            const isDB = tier.prize_tier === '0';

            let tierClasses = `prize-tier ${config.css}`;
            if (hasMatch) {
                tierClasses += ' has-match';
                if (isDB) tierClasses += ' tier-db';
                tierClasses += ' open';  // Auto-expand tiers with matches
            }

            const matchBadge = hasMatch
                ? `<span class="prize-tier__match-count match-found">${tier.match_count} lần trúng</span>`
                : `<span class="prize-tier__match-count match-none">0</span>`;

            const desc = buildDescription(tier.suffix, tier.digits_matched, tier.prize_tier);

            // Detail rows
            let detailHTML = '';
            if (hasMatch) {
                const rows = tier.matches.map(m => `
                    <a href="${m.link}" target="_blank" rel="noopener" class="prize-detail-item" onclick="event.stopPropagation()">
                        <span class="prize-detail__number">
                            ${highlightNumber(m.number, tier.suffix, tier.digits_matched)}
                        </span>
                        <div class="prize-detail__meta">
                            <p class="prize-detail__province">${m.province} (${m.region_name})</p>
                            <p class="prize-detail__date">${formatDate(m.draw_date)} · ${formatDaysAgo(m.days_ago)} ↗</p>
                        </div>
                    </a>
                `).join('');
                detailHTML = `<div class="prize-detail-list">${rows}</div>`;
            } else {
                detailHTML = `
                    <div class="prize-detail-list">
                        <div class="empty-state" style="padding: 20px;">
                            <p class="empty-state__text" style="font-size:0.85rem">Không tìm thấy lần trúng nào</p>
                        </div>
                    </div>`;
            }

            const tierHTML = `
                <div class="${tierClasses}" onclick="toggleTier(this)">
                    <div class="prize-tier__header">
                        <div class="prize-tier__left">
                            <div class="prize-tier__badge">${config.badge}</div>
                            <div class="prize-tier__info">
                                <h4>${config.label}</h4>
                                <p>${desc}</p>
                            </div>
                        </div>
                        <div class="prize-tier__right">
                            <span class="prize-tier__value">${formatMoney(tier.prize_value)} đồng</span>
                            ${matchBadge}
                            <span class="prize-tier__expand">▼</span>
                        </div>
                    </div>
                    <div class="prize-tier__details">${detailHTML}</div>
                </div>
            `;
            container.insertAdjacentHTML('beforeend', tierHTML);
        }
    }

    // ================================================================
    // EVENT HANDLERS
    // ================================================================
    const ticketInput = document.getElementById('ticketInput');

    // Only allow digits, max 6
    ticketInput.addEventListener('input', (e) => {
        e.target.value = e.target.value.replace(/\D/g, '').slice(0, 6);
    });

    // Region chips toggle
    document.querySelectorAll('.region-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            e.target.classList.toggle('active');
        });
    });

    // Prize tier expand/collapse
    function toggleTier(el) {
        el.classList.toggle('open');
    }

    // Search
    async function doSearch() {
        const number = ticketInput.value.trim();
        if (number.length < 2) {
            ticketInput.focus();
            return;
        }

        // Get active regions
        const regions = [];
        document.querySelectorAll('.region-chip.active').forEach(chip => {
            regions.push(chip.dataset.region);
        });
        if (regions.length === 0) {
            alert('Vui lòng chọn ít nhất 1 vùng miền!');
            return;
        }

        // Show loading
        document.getElementById('loader').classList.add('visible');
        document.getElementById('resultsSection').classList.remove('visible');

        try {
            const response = await fetch('http://localhost:8000/api/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ number, regions }),
            });

            if (!response.ok) {
                let errMsg = `Server error (${response.status})`;
                try {
                    const errBody = await response.text();
                    const errJson = JSON.parse(errBody);
                    errMsg = errJson.detail?.[0]?.msg || errJson.detail || errMsg;
                } catch (_) { /* ignore parse errors */ }
                throw new Error(errMsg);
            }

            const data = await response.json();

            document.getElementById('loader').classList.remove('visible');
            document.getElementById('resultsSection').classList.add('visible');
            renderResults(data);

        } catch (err) {
            document.getElementById('loader').classList.remove('visible');
            alert('Lỗi khi tra cứu: ' + err.message);
        }
    }

    document.getElementById('searchBtn').addEventListener('click', (e) => {
        e.preventDefault();
        doSearch();
    });

    // Enter key to search
    ticketInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            doSearch();
        }
    });

    // Auto-focus input on load
    ticketInput.focus();
-- ==========================================================
-- Real-Time Airfare Price Index (APIx) Database Schema
-- Database Engine: MariaDB / MySQL
-- ==========================================================

CREATE DATABASE IF NOT EXISTS apix_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE apix_db;

-- 1. Representative Route Basket (DGCA Traffic Weights)
CREATE TABLE IF NOT EXISTS routes (
    route_id INT AUTO_INCREMENT PRIMARY KEY,
    route_code VARCHAR(20) NOT NULL UNIQUE,      -- e.g. 'DEL-BOM'
    origin VARCHAR(10) NOT NULL,                 -- e.g. 'DEL'
    destination VARCHAR(10) NOT NULL,            -- e.g. 'BOM'
    origin_city VARCHAR(50) NOT NULL,            -- e.g. 'New Delhi'
    dest_city VARCHAR(50) NOT NULL,              -- e.g. 'Mumbai'
    dgca_weight DECIMAL(6, 4) NOT NULL,          -- Passenger traffic share (e.g. 0.1850)
    base_price_p0 DECIMAL(10, 2) NOT NULL,       -- Base period reference price in INR (P0)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Scraped Airfare Quotes (Cleaned & Normalized)
CREATE TABLE IF NOT EXISTS airfare_quotes (
    quote_id INT AUTO_INCREMENT PRIMARY KEY,
    route_code VARCHAR(20) NOT NULL,             -- e.g. 'DEL-BOM'
    carrier VARCHAR(50) NOT NULL,                -- IndiGo, Air India, Akasa Air, SpiceJet
    flight_number VARCHAR(20) NOT NULL,          -- e.g. '6E-2054'
    departure_time VARCHAR(20),                  -- e.g. '06:00'
    arrival_time VARCHAR(20),                    -- e.g. '08:15'
    advance_days INT NOT NULL,                   -- 1, 7, 15, 30, 45 (T+N days)
    departure_date DATE NOT NULL,                -- Date of travel
    base_fare DECIMAL(10, 2) NOT NULL,           -- Base ticket price
    taxes_fees DECIMAL(10, 2) NOT NULL,          -- GST, User Dev Fee (UDF), Passenger Service Fee
    udf_charges DECIMAL(10, 2) DEFAULT 0.00,     -- Separated UDF
    total_fare DECIMAL(10, 2) NOT NULL,          -- Total price paid by passenger
    source_portal VARCHAR(50) DEFAULT 'Direct',  -- Direct Airline, MakeMyTrip, EaseMyTrip
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_route_date (route_code, departure_date),
    INDEX idx_advance_days (advance_days)
) ENGINE=InnoDB;

-- 3. Computed Airfare Price Index (APIx) History
CREATE TABLE IF NOT EXISTS apix_history (
    index_id INT AUTO_INCREMENT PRIMARY KEY,
    calc_date DATE NOT NULL,
    headline_apix DECIMAL(8, 2) NOT NULL,        -- Composite Laspeyres Index (Base 100.0)
    apix_t1 DECIMAL(8, 2),                       -- T+1 Advance Window Index
    apix_t7 DECIMAL(8, 2),                       -- T+7 Advance Window Index
    apix_t15 DECIMAL(8, 2),                      -- T+15 Advance Window Index
    apix_t30 DECIMAL(8, 2),                      -- T+30 Advance Window Index
    apix_t45 DECIMAL(8, 2),                      -- T+45 Advance Window Index
    sample_size INT DEFAULT 0,                   -- Number of quotes included in calculation
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ==========================================================
-- Seed Data: Top Indian Domestic Routes by DGCA Traffic Share
-- ==========================================================
INSERT INTO routes (route_code, origin, destination, origin_city, dest_city, dgca_weight, base_price_p0)
VALUES
    ('DEL-BOM', 'DEL', 'BOM', 'Delhi', 'Mumbai', 0.1850, 4850.00),
    ('DEL-BLR', 'DEL', 'BLR', 'Delhi', 'Bengaluru', 0.1420, 5400.00),
    ('BOM-BLR', 'BOM', 'BLR', 'Mumbai', 'Bengaluru', 0.1100, 3950.00),
    ('DEL-CCU', 'DEL', 'CCU', 'Delhi', 'Kolkata', 0.0950, 4900.00),
    ('BLR-HYD', 'BLR', 'HYD', 'Bengaluru', 'Hyderabad', 0.0880, 2800.00),
    ('MAA-DEL', 'MAA', 'DEL', 'Chennai', 'Delhi', 0.0820, 5200.00),
    ('BOM-GOI', 'BOM', 'GOI', 'Mumbai', 'Goa', 0.0780, 3200.00),
    ('DEL-HYD', 'DEL', 'HYD', 'Delhi', 'Hyderabad', 0.0750, 4300.00),
    ('DEL-PNQ', 'DEL', 'PNQ', 'Delhi', 'Pune', 0.0730, 4600.00),
    ('BOM-MAA', 'BOM', 'MAA', 'Mumbai', 'Chennai', 0.0720, 3850.00)
ON DUPLICATE KEY UPDATE 
    dgca_weight = VALUES(dgca_weight),
    base_price_p0 = VALUES(base_price_p0);

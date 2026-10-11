CREATE TABLE territory (
    state TEXT PRIMARY KEY,
    wind_hail_band TEXT NOT NULL,
    wildfire_band TEXT NOT NULL
);

INSERT INTO territory (state, wind_hail_band, wildfire_band) VALUES
    ('WI', 'low', 'low'),
    ('OK', 'high', 'low'),
    ('CO', 'high', 'high');

CREATE TABLE credit (
    applicant_id TEXT PRIMARY KEY,
    bureau_score INTEGER,
    delinquencies INTEGER
);

INSERT INTO credit (applicant_id, bureau_score, delinquencies) VALUES
    ('APP-APPROVE', 740, 0),
    ('APP-REFER', 740, 0),
    ('APP-RETRY', 740, 0),
    ('APP-TIMEOUT', 740, 0);

-- SQL Script to Create Learned Ingredient Aliases Table
-- Run this in your Railway PostgreSQL console (Database tab)

CREATE TABLE learned_ingredient_aliases (
    id SERIAL PRIMARY KEY,
    alias_text VARCHAR(255) NOT NULL UNIQUE,
    ingredient_id INTEGER NOT NULL REFERENCES ingredients(id),  -- Links to existing table!
    confidence DECIMAL(3,2) NOT NULL,
    usage_count INTEGER DEFAULT 1,
    learned_date TIMESTAMP DEFAULT NOW(),
    last_used TIMESTAMP DEFAULT NOW(),
    source VARCHAR(50) DEFAULT 'llm',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX idx_alias_text ON learned_ingredient_aliases(alias_text);
CREATE INDEX idx_ingredient_id ON learned_ingredient_aliases(ingredient_id);
CREATE INDEX idx_usage_count ON learned_ingredient_aliases(usage_count DESC);

-- Verify table was created
SELECT table_name
FROM information_schema.tables
WHERE table_name = 'learned_ingredient_aliases';

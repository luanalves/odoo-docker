# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Feature 026: adiciona índice em real_estate_agent.user_id.

    real.estate.agent.user_id passa a ser um filtro de RBAC ativamente
    consultado em toda listagem de imóveis/leads feita por um agente
    convidado via POST /api/v1/users/invite (antes, o campo ficava quase
    sempre nulo e a consulta raramente batia). Ver spec-idea.md NFR2/FR6.2.
    """
    cr.execute(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'real_estate_agent'
        )
        """
    )
    table_exists = cr.fetchone()[0]
    if not table_exists:
        _logger.info("Feature 026: tabela real_estate_agent ainda não existe, pulando migração.")
        return

    cr.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_real_estate_agent_user_id
        ON real_estate_agent (user_id);
        """
    )
    _logger.info("Feature 026: índice idx_real_estate_agent_user_id garantido em real_estate_agent.")

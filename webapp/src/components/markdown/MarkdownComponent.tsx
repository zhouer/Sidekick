// webapp/src/components/markdown/MarkdownComponent.tsx
import React, { forwardRef, useMemo } from 'react';
import ReactMarkdown, { Options as ReactMarkdownOptions } from 'react-markdown';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import './MarkdownComponent.css';
import { MarkdownState } from './types';
import { ComponentHandle } from '../../types';

interface MarkdownComponentProps {
    id: string;
    state: MarkdownState;
}

const customSchema = {
    ...defaultSchema,
    attributes: {
        ...defaultSchema.attributes,
        code: [
            ...(defaultSchema.attributes?.code || []).filter(
                attr => typeof attr === 'string' ? attr !== 'className' : attr[0] !== 'className'
            ),
            ['className', /^language-\w+$/] // 允許 class="language-anyword"
        ],
    },
};

const MarkdownComponent = forwardRef<ComponentHandle | null, MarkdownComponentProps>(
    ({ id, state }, ref) => {
        const { source } = state;

        const rehypePlugins: ReactMarkdownOptions['rehypePlugins'] = useMemo(() => [
            [rehypeSanitize, customSchema]
        ], []);


        return (
            <div className="markdown-component" data-testid={`markdown-${id}`}>
                <ReactMarkdown rehypePlugins={rehypePlugins}>
                    {source}
                </ReactMarkdown>
            </div>
        );
    }
);
MarkdownComponent.displayName = 'MarkdownComponent';
export default MarkdownComponent;
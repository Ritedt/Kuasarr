import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Search,
  Download,
  FileText,
  HardDrive,
  Calendar,
  ExternalLink,
  Filter,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { Layout } from '../components/layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Spinner } from '../components/ui/Spinner';
import { search, downloadSearchResult, getCategories } from '../lib/api';
import { useUIStore } from '../stores/uiStore';
import type { SearchResult, Category } from '../types';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
}

function SearchResultRow({
  result,
  onDownload,
  categories,
  isPending,
}: {
  result: SearchResult;
  onDownload: (resultId: string, categoryId?: string) => void;
  categories: Category[];
  isPending: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('');

  const categoryOptions = [
    { value: '', label: 'Default Category' },
    ...categories.map((cat) => ({ value: cat.id, label: cat.name })),
  ];

  return (
    <div className="border-b border-bg-tertiary last:border-0">
      <div
        className="p-4 hover:bg-bg-tertiary/30 transition-colors cursor-pointer"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-medium text-text-primary truncate">{result.title}</h3>
              {result.quality && (
                <Badge variant="info" size="sm">
                  {result.quality}
                </Badge>
              )}
              {result.language && (
                <Badge variant="default" size="sm">
                  {result.language}
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-4 text-sm text-text-secondary">
              <span className="flex items-center gap-1">
                <HardDrive className="h-3.5 w-3.5" />
                {formatBytes(result.size)}
              </span>
              <span className="flex items-center gap-1">
                <Calendar className="h-3.5 w-3.5" />
                {result.age}
              </span>
              <span>{result.hoster}</span>
              <Badge variant="primary" size="sm">
                {result.category}
              </Badge>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onDownload(result.id, selectedCategory || undefined);
              }}
              disabled={isPending}
              leftIcon={<Download className="h-4 w-4" />}
            >
              Download
            </Button>
            <Button variant="ghost" size="sm">
              {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="px-4 pb-4 pt-0">
          <div className="bg-bg-tertiary/50 rounded-lg p-4 space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-text-secondary">Grabs</p>
                <p className="text-text-primary font-medium">{result.grabs}</p>
              </div>
              {result.seeders !== undefined && (
                <div>
                  <p className="text-text-secondary">Seeders</p>
                  <p className="text-text-primary font-medium">{result.seeders}</p>
                </div>
              )}
              {result.leechers !== undefined && (
                <div>
                  <p className="text-text-secondary">Leechers</p>
                  <p className="text-text-primary font-medium">{result.leechers}</p>
                </div>
              )}
              {result.imdb_id && (
                <div>
                  <p className="text-text-secondary">IMDb</p>
                  <a
                    href={`https://www.imdb.com/title/${result.imdb_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-kuasarr-primary hover:underline flex items-center gap-1"
                  >
                    {result.imdb_id}
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}
            </div>

            <div className="flex items-center gap-4 pt-2 border-t border-bg-tertiary">
              <div className="flex-1 max-w-xs">
                <Select
                  label="Category"
                  options={categoryOptions}
                  value={selectedCategory}
                  onChange={setSelectedCategory}
                />
              </div>
              {result.password && (
                <div className="text-sm">
                  <span className="text-text-secondary">Password: </span>
                  <span className="text-text-primary font-mono">{result.password}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function SearchPage() {
  const { jdConnected } = useUIStore();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [sortBy, setSortBy] = useState<'relevance' | 'size' | 'age' | 'grabs'>('relevance');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [hasSearched, setHasSearched] = useState(false);

  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: getCategories,
  });

  const {
    data: searchResults = [],
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['search', searchQuery, selectedCategory],
    queryFn: () => search({ query: searchQuery, category: selectedCategory || undefined }),
    enabled: hasSearched && searchQuery.length > 0,
  });

  const downloadMutation = useMutation({
    mutationFn: ({ resultId, categoryId }: { resultId: string; categoryId?: string }) =>
      downloadSearchResult({ result_id: resultId, category_id: categoryId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['packages'] });
    },
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setHasSearched(true);
      refetch();
    }
  };

  const sortedResults = [...searchResults].sort((a, b) => {
    let comparison = 0;
    switch (sortBy) {
      case 'size':
        comparison = a.size - b.size;
        break;
      case 'age':
        comparison = a.age.localeCompare(b.age);
        break;
      case 'grabs':
        comparison = a.grabs - b.grabs;
        break;
      default:
        return 0;
    }
    return sortOrder === 'asc' ? comparison : -comparison;
  });

  const categoryOptions = [
    { value: '', label: 'All Categories' },
    ...categories.map((cat) => ({ value: cat.id, label: cat.name })),
  ];

  const sortOptions = [
    { value: 'relevance', label: 'Relevance' },
    { value: 'size', label: 'Size' },
    { value: 'age', label: 'Age' },
    { value: 'grabs', label: 'Grabs' },
  ];

  return (
    <Layout jdConnected={jdConnected}>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Search</h1>
          <p className="text-text-secondary mt-1">Find and download content from configured hosters</p>
        </div>

        <Card>
          <CardContent className="p-6">
            <form onSubmit={handleSearch} className="space-y-4">
              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex-1">
                  <Input
                    placeholder="Search for movies, TV shows, books..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    leftIcon={<Search className="h-4 w-4" />}
                    className="h-12"
                  />
                </div>
                <div className="flex gap-2">
                  <Select
                    options={categoryOptions}
                    value={selectedCategory}
                    onChange={setSelectedCategory}
                    className="w-48"
                  />
                  <Button
                    type="submit"
                    variant="primary"
                    size="lg"
                    loading={isLoading}
                    disabled={!searchQuery.trim()}
                    leftIcon={<Search className="h-5 w-5" />}
                  >
                    Search
                  </Button>
                </div>
              </div>

              <div className="flex items-center gap-4 pt-2 border-t border-bg-tertiary">
                <div className="flex items-center gap-2">
                  <Filter className="h-4 w-4 text-text-secondary" />
                  <span className="text-sm text-text-secondary">Sort by:</span>
                  <Select
                    options={sortOptions}
                    value={sortBy}
                    onChange={(value) => setSortBy(value as typeof sortBy)}
                    className="w-32"
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')}
                  >
                    {sortOrder === 'asc' ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>

        {!hasSearched ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16">
              <Search className="h-16 w-16 text-text-secondary/50 mb-4" />
              <h3 className="text-lg font-medium text-text-primary">Start Searching</h3>
              <p className="text-text-secondary text-sm mt-1 text-center max-w-md">
                Enter a search term above to find content from your configured hosters. Results will appear here.
              </p>
            </CardContent>
          </Card>
        ) : isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner size="xl" />
          </div>
        ) : sortedResults.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-16">
              <FileText className="h-16 w-16 text-text-secondary/50 mb-4" />
              <h3 className="text-lg font-medium text-text-primary">No Results Found</h3>
              <p className="text-text-secondary text-sm mt-1 text-center max-w-md">
                No results found for &quot;{searchQuery}&quot;. Try a different search term or check your hoster configuration.
              </p>
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>Search Results ({sortedResults.length})</span>
                <Badge variant="primary">{searchQuery}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {sortedResults.map((result) => (
                <SearchResultRow
                  key={result.id}
                  result={result}
                  onDownload={(resultId, categoryId) => downloadMutation.mutate({ resultId, categoryId })}
                  categories={categories}
                  isPending={downloadMutation.isPending}
                />
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </Layout>
  );
}
